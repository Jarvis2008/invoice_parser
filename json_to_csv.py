import json
import csv

# Specify the input JSON file and output CSV file names
input_json_file = "linefields.json"
output_csv_file = "2925323968.csv"

# Read JSON from the file
def read_json(file_path):
    """
    Reads JSON data from a file.
    
    Parameters:
        file_path (str): Path to the JSON file.
    
    Returns:
        dict: Parsed JSON data.
    """
    with open(file_path, "r") as file:
        return json.load(file)

# Convert JSON to CSV
def convert_json_to_csv(json_data, csv_file):
    """
    Converts JSON data to a CSV file.
    
    Parameters:
        json_data (dict): JSON data to convert.
        csv_file (str): Output CSV file name.
    """
    # Extract the list of line items
    line_items = json_data.get("LineItems", [])
    
    if not line_items:
        print("No line items found in JSON data.")
        return
    
    # Open the file in write mode
    with open(csv_file, mode="w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=line_items[0].keys())
        
        # Write the header
        writer.writeheader()
        
        # Write each line item
        writer.writerows(line_items)

# Main script execution
if __name__ == "__main__":
    try:
        # Load the JSON data
        data = read_json(input_json_file)
        
        # Convert the JSON data to CSV
        convert_json_to_csv(data, output_csv_file)
        
        print(f"JSON data successfully written to {output_csv_file}")
    except FileNotFoundError:
        print(f"Error: {input_json_file} not found.")
    except json.JSONDecodeError:
        print(f"Error: Failed to parse JSON in {input_json_file}.")
