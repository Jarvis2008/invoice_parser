import streamlit as st
import json
import pandas as pd
from io import StringIO
import base64

def process_json_data(input_json):
    # Parse the JSON if it's a string, otherwise use as is
    if isinstance(input_json, str):
        data = json.loads(input_json)
    else:
        data = input_json
    
    # Process each line item
    for item in data["LineItems"]:
        # Convert Rate to float, removing any commas if present
        rate = float(item["Rate"].replace(",", ""))
        # Calculate P Rate (1.06 times Rate) and format to 2 decimal places
        p_rate = round(rate * 1.06, 2)
        b_rate=round(p_rate*1.11,2)
        # Create a new dictionary with all original items plus P Rate
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
    
    return data

def json_to_csv(json_data):
    # Convert the LineItems to a DataFrame
    df = pd.DataFrame(json_data["LineItems"])
    return df

def get_download_link(df, filename):
    """Generates a link to download the CSV file"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}.csv">Download CSV File</a>'
    return href

def main():
    st.title("JSON to CSV Converter")
    st.write("Upload a JSON file and convert it to CSV with additional P Rate column")
    
    # File uploader
    uploaded_file = st.file_uploader("Choose a JSON file", type="json")
    
    # Text input for filename
    filename = st.text_input("Enter filename for the CSV (without extension)", "processed_data")
    
    if uploaded_file is not None:
        try:
            # Read and process the JSON file
            json_content = json.load(uploaded_file)
            processed_data = process_json_data(json_content)
            
            # Convert to DataFrame
            df = json_to_csv(processed_data)
            
            # Display preview of the data
            st.write("Preview of processed data:")
            st.dataframe(df.head())
            
            # Create download link
            st.markdown(get_download_link(df, filename), unsafe_allow_html=True)
            
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()