from dotenv import load_dotenv
import google.generativeai as genai
import os
import json
import fitz  # PyMuPDF
from PIL import Image
import io
import tempfile
import time
import atexit

load_dotenv()
genai.configure(api_key=os.environ['GEMINI_API_KEY'])
model = genai.GenerativeModel(model_name='gemini-2.0-flash')

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

def process_pdf_to_json(pdf_path, system_prompt,pages):
    """
    Processes a PDF file page by page and extracts invoice line items to JSON.
    
    Args:
        pdf_path: Path to the PDF file
        system_prompt: Detailed system prompt for Gemini with extraction instructions
        
    Returns:
        Combined JSON with all invoice line items
    """
    all_line_items = []
    
    # Open PDF file
    try:
        pdf_document = fitz.open(pdf_path)
        
        # Process each page
        for page_num in range(pages):
            # Render page to image
            page = pdf_document.load_page(page_num)
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
                
            except Exception as e:
                print(f"Error processing page {page_num + 1}: {e}")
                print(f"Response text: {response.text if 'response' in locals() else 'No response'}")
            
            # Don't try to delete the file here, it will be cleaned up at exit
                
        # Create final combined structure
        combined_data = {"LineItems": all_line_items}
        return combined_data
    
    except Exception as e:
        print(f"Error opening PDF: {e}")
        return None
    finally:
        # Make sure to close the PDF document
        if 'pdf_document' in locals():
            pdf_document.close()

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

if __name__ == "__main__":
    pdf_file = "2925365390.pdf"
    
    system_prompt = """
    You are a precise and detail-oriented invoice data extraction assistant. Your task is to analyze the provided invoice and extract all line items into a structured JSON array. Each line item should be represented as an individual JSON object, and all specified fields should be included for every line item. If a field is missing or not identifiable for a specific line item, use an empty string ("") as its value.
    
    Fields to Extract for Each Line Item:
    Description of Goods: Description of the items or services listed in the invoice.
    HSN/SAC: Harmonized System of Nomenclature or Service Accounting Code.
    Batch No: Batch number associated with the goods.
    Mfg Date: Manufacturing date of the goods.
    Expiry Date: Expiry date of the goods.
    MRP: Maximum Retail Price of the item.
    QTY: Quantity of the goods.
    UOM: Unit of Measure for the quantity (e.g., pcs, kg, ltr).
    Rate: Price per unit of the goods.
    Discount%: Discount percentage applied.
    Discount Value: Total discount value in currency.
    Taxable Value: Total amount before taxes after applying discounts.
    IGST Rate: Integrated GST rate applied.
    IGST Amount: Total Integrated GST amount applied.
    Total: Grand total amount for the line item, including all taxes.
    
    Output Format:
    The output should be a JSON object containing a key "LineItems", whose value is a list of JSON objects, one for each line item. For example:
    {
        "LineItems": [
            {
                "Description of Goods": "Item 1 Description",
                "HSN/SAC": "1234",
                "Batch No": "B001",
                "Mfg Date": "2024-01-01",
                "Expiry Date": "2025-01-01",
                "MRP": "500.00",
                "QTY": "2",
                "UOM": "pcs",
                "Rate": "450.00",
                "Discount%": "10",
                "Discount Value": "90.00",
                "Taxable Value": "810.00",
                "IGST Rate": "18",
                "IGST Amount": "145.80",
                "Total": "955.80"
            }
        ]
    }
    
    Instructions:
    Extract every line item in the invoice and structure it as described above.
    Include all fields for each line item. If a field is not present for a line item, return an empty string ("").
    Ensure numerical fields are extracted accurately, retaining precision.
    Provide the complete structured JSON output, even if the invoice contains a single line item.
    """
    
    result = process_pdf_to_json(pdf_file, system_prompt,2)
    
    if result and "LineItems" in result:
        # Validate and ensure all fields are present
        result["LineItems"] = validate_line_items(result["LineItems"])
        
        # Save combined results to file
        with open("invoice_line_items.json", "w") as f:
            json.dump(result,f, indent=2)
        print(f"Successfully extracted {len(result['LineItems'])} line items to invoice_line_items.json")
    
    # Final cleanup attempt for any remaining temp files
    cleanup_temp_files()