import streamlit as st
import json
import pandas as pd
from io import StringIO
import base64
import os
import io
import tempfile
import time
import atexit
import fitz  # PyMuPDF
from PIL import Image
from dotenv import load_dotenv
import google.generativeai as genai

# Set page config
st.set_page_config(page_title="Invoice PDF Processor", layout="wide")

# Load environment variables and configure Gemini
load_dotenv()

# Initialize Gemini API
@st.cache_resource
def initialize_gemini():
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        api_key = st.secrets.get("GEMINI_API_KEY", None)
    
    if not api_key:
        st.error("Gemini API key not found. Please set GEMINI_API_KEY in .env file or Streamlit secrets.")
        return None
    
    genai.configure(api_key=api_key)
    return genai.GenerativeModel(model_name='gemini-2.0-flash')

model = initialize_gemini()

# Keep track of temporary files to clean up at exit
temp_files = []

def cleanup_temp_files():
    """Clean up any remaining temporary files when the program exits"""
    for file_path in temp_files:
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
        except Exception as e:
            print(f"Warning: Could not delete temporary file {file_path}: {e}")

# Register the cleanup function to run at exit
atexit.register(cleanup_temp_files)

def process_pdf_to_json(pdf_file, system_prompt, page_limit=None):
    """
    Processes a PDF file and extracts invoice line items to JSON.
    
    Args:
        pdf_file: PDF file object
        system_prompt: Detailed system prompt for Gemini with extraction instructions
        page_limit: Maximum number of pages to process
        
    Returns:
        Combined JSON with all invoice line items
    """
    all_line_items = []
    progress_text = st.empty()
    progress_bar = st.progress(0)
    
    # Save uploaded file to a temporary file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as temp_pdf:
        temp_pdf.write(pdf_file.getvalue())
        temp_pdf_path = temp_pdf.name
    
    try:
        # Open PDF file
        pdf_document = fitz.open(temp_pdf_path)
        total_pages = len(pdf_document)
        
        # Apply page limit if specified
        if page_limit and page_limit < total_pages:
            pages_to_process = page_limit
        else:
            pages_to_process = total_pages
        
        # Process each page
        for page_idx in range(pages_to_process):
            progress_text.text(f"Processing page {page_idx + 1} of {pages_to_process}...")
            progress_bar.progress((page_idx + 1) / pages_to_process)
            
            # Render page to image
            page = pdf_document.load_page(page_idx)
            pix = page.get_pixmap(alpha=False)
            
            # Create a temporary file
            temp_file = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            temp_path = temp_file.name
            temp_files.append(temp_path)  # Add to tracking list
            temp_file.close()  # Close the file handle immediately
            
            # Save the pixmap to the temp file
            pix.save(temp_path)
            
            try:
                # Open, process and explicitly close the image
                with Image.open(temp_path) as img:
                    # Convert image to bytes
                    img_bytes = io.BytesIO()
                    img.save(img_bytes, format="JPEG")
                    img_bytes = img_bytes.getvalue()
                
                # Process with Gemini
                if model:
                    content = [
                        {"role": "user", "parts": [{"text": system_prompt}]},
                        {"role": "user", "parts": [
                            {"inline_data": {"mime_type": "image/jpeg", "data": img_bytes}},
                            {"text": "Extract all line items from this invoice page and format as specified."}
                        ]}
                    ]
                    
                    response = model.generate_content(
                        contents=content,
                        generation_config=genai.types.GenerationConfig(
                            response_mime_type="application/json"
                        )
                    )
                    
                    # Parse the JSON response
                    page_data = json.loads(response.text)
                    
                    # Add line items to combined data
                    if "LineItems" in page_data and isinstance(page_data["LineItems"], list):
                        all_line_items.extend(page_data["LineItems"])
                else:
                    progress_text.text("Gemini API not properly initialized")
                    break
                
            except Exception as e:
                st.error(f"Error processing page {page_idx + 1}: {str(e)}")
                if 'response' in locals():
                    st.error(f"Response text: {response.text}")
        
        # Clear progress indicators
        progress_text.empty()
        progress_bar.empty()
        
        # Create final combined structure
        combined_data = {"LineItems": all_line_items}
        return combined_data
    
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        return None
    finally:
        # Make sure to close the PDF document and remove temp file
        if 'pdf_document' in locals():
            pdf_document.close()
        if os.path.exists(temp_pdf_path):
            os.unlink(temp_pdf_path)

def validate_line_items(line_items):
    """
    Validates and ensures all required fields are present in line items.
    If fields are missing, adds them with empty string values.
    """
    required_fields = [
        "Description of Goods", "HSN/SAC", "Batch No", "Mfg Date", "Expiry Date", 
        "MRP", "QTY", "UOM", "Rate", "Discount%", "Discount Value", 
        "Taxable Value", "IGST Rate", "IGST Amount", "Total"
    ]
    
    for item in line_items:
        for field in required_fields:
            if field not in item:
                item[field] = ""
    
    return line_items

def process_json_data(input_json):
    """Add calculated fields to the JSON data"""
    # Process each line item
    for item in input_json["LineItems"]:
        # Convert Rate to float, removing any commas if present
        try:
            rate = float(item["Rate"].replace(",", "")) if item["Rate"] else 0
            # Calculate P Rate (1.06 times Rate) and format to 2 decimal places
            p_rate = round(rate * 1.06, 2)
            b_rate = round(p_rate * 1.11, 2)
            
            # Create a new dictionary with all original items plus P Rate and B Rate
            new_item = {}
            for key, value in item.items():
                new_item[key] = value
                if key == "Rate":
                    new_item["P Rate"] = f"{p_rate:.2f}"
                if key == "Total":
                    new_item["B Rate"] = f"{b_rate:.2f}" 
            
            # Replace the original item with the new one
            item.clear()
            item.update(new_item)
        except (ValueError, TypeError) as e:
            # Handle case where Rate is not a valid number
            item["P Rate"] = ""
            item["B Rate"] = ""
    
    return input_json

def json_to_csv(json_data):
    """Convert JSON data to a DataFrame"""
    df = pd.DataFrame(json_data["LineItems"])
    return df

def get_download_link(df, filename):
    """Generates a link to download the CSV file"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}.csv" class="download-button">Download CSV File</a>'
    return href

def main():
    st.title("Invoice PDF Processor")
    st.write("Upload a PDF invoice to extract line items and download as CSV")
    
    # File uploader
    uploaded_file = st.file_uploader("Choose a PDF file", type="pdf")
    
    # Page limit input
    page_limit = st.number_input("Page limit (leave at 0 for all pages)", min_value=0, value=0)
    
    # Only show processing button when a file is uploaded
    if uploaded_file is not None:
        filename = os.path.splitext(uploaded_file.name)[0]  # Get filename without extension
        
        st.subheader("Processing Options")
        process_button = st.button("Process Invoice")
        
        if process_button:
            with st.spinner("Processing PDF..."):
                # System prompt for Gemini
                system_prompt = """
                You are a precise and detail-oriented invoice data extraction assistant. Your task is to analyze the provided invoice and extract all line items into a structured JSON array. Each line item should be represented as an individual JSON object, and all specified fields should be included for every line item. If a field is missing or not identifiable for a specific line item, use an empty string ("") as its value.
                
                Fields to Extract for Each Line Item:
                Description of Goods: Description of the items or services listed in the invoice. Don't include mrp in the description.
                HSN/SAC: Harmonized System of Nomenclature or Service Accounting Code.
                Batch No: Batch number associated with the goods.
                Mfg Date: Manufacturing date of the goods.
                Expiry Date: Expiry date of the goods.
                MRP: Maximum Retail Price of the item.
                QTY: Quantity of the goods. It contains upto three decimal points so don't add the last 0 anywhere else if it is in another line.
                UOM: Unit of Measure for the quantity (e.g., pcs, kg, ltr). 
                Rate: Price per unit of the goods.
                Discount%: Discount percentage applied.
                Discount Value: Total discount value in currency.
                Taxable Value: Total amount before taxes after applying discounts.
                IGST Rate: Integrated GST rate applied.
                IGST Amount: Total Integrated GST amount applied.
                Total: Grand total amount for the line item, including all taxes.
                
                Output Format:
                The output should be a JSON object containing a key "LineItems", whose value is a list of JSON objects, one for each line item.
                
                Instructions:
                Extract every line item in the invoice and structure it as described above.
                Include all fields for each line item. If a field is not present for a line item, return an empty string ("").
                Ensure numerical fields are extracted accurately, retaining precision.
                Provide the complete structured JSON output, even if the invoice contains a single line item.
                Keep the column value as single string don't make multiple lines.
                """
                
                # Process the PDF
                page_limit_to_use = page_limit if page_limit > 0 else None
                extracted_data = process_pdf_to_json(uploaded_file, system_prompt, page_limit_to_use)
                
                if extracted_data and "LineItems" in extracted_data and extracted_data["LineItems"]:
                    # Validate and process the data
                    extracted_data["LineItems"] = validate_line_items(extracted_data["LineItems"])
                    processed_data = process_json_data(extracted_data)
                    
                    # Convert to DataFrame
                    df = json_to_csv(processed_data)
                    
                    # Display statistics
                    st.success(f"Successfully extracted {len(df)} line items from the invoice")
                    
                    # Display preview of the data
                    st.subheader("Preview of Extracted Data")
                    st.dataframe(df.head(10))
                    
                    # Create download link with the same name as the input file
                    st.markdown(f"### Download Processed Data")
                    st.markdown(get_download_link(df, filename), unsafe_allow_html=True)
                    
                    # Add CSS for download button
                    st.markdown("""
                    <style>
                    .download-button {
                        display: inline-block;
                        padding: 0.5em 1em;
                        color: white;
                        background-color: #0066cc;
                        text-decoration: none;
                        border-radius: 4px;
                        font-weight: bold;
                    }
                    .download-button:hover {
                        background-color: #0052a3;
                    }
                    </style>
                    """, unsafe_allow_html=True)
                else:
                    st.error("No line items were extracted from the PDF. Please check if the invoice format is supported.")

    # Instructions
    with st.expander("How to use this app"):
        st.markdown("""
        1. Upload a PDF invoice using the file uploader
        2. Set a page limit if you only want to process specific pages (optional)
        3. Click 'Process Invoice' to start extraction
        4. Review the extracted data preview
        5. Download the CSV file with the same name as your input PDF
        
        **Note:** Processing large PDFs may take some time. The app extracts line items page by page.
        """)

if __name__ == "__main__":
    main()
    # Final cleanup attempt for any remaining temp files
    cleanup_temp_files()