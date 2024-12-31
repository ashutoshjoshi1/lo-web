import os
import bz2
import pandas as pd
from dash import Dash, dcc, html, Input, Output
import dash_bootstrap_components as dbc
import plotly.express as px
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://data.ovh.pandonia-global-network.org/"

# Initialize the Dash app
app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
server = app.server
app.title = "Pandonia Data Viewer - L0"
uploaded_df = None  # Global variable to hold the DataFrame

def list_items(base_url):
    """List items available at the given URL."""
    try:
        response = requests.get(base_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        items = [
            link["href"].lstrip("./").rstrip("/")
            for link in soup.find_all("a", href=True)
            if link["href"].startswith("./")
        ]
        return items
    except Exception as e:
        print(f"Error listing items: {e}")
        return []

def fetch_file(file_url):
    """Fetch file content from the given URL."""
    try:
        response = requests.get(file_url)
        response.raise_for_status()
        return response.content
    except Exception as e:
        print(f"Error fetching file: {e}")
        return None

def decompress_bz2_file(file_content):
    """Decompress a .bz2 file and return its content as a string."""
    try:
        decompressed_content = bz2.decompress(file_content).decode("utf-8", errors="replace")
        return decompressed_content
    except Exception as e:
        print(f"Error decompressing file: {e}")
        return ""

def process_txt_file(file_content):
    """Process the TXT file content, handling metadata and aggregating pixel values."""
    try:
        # Split file into lines
        lines = file_content.split("\n")
        data_start = 0

        # Find the start of the data section
        for i, line in enumerate(lines):
            if line.startswith("---------------------------------------------------------------------------------------"):
                data_start = i + 1
                break

        # Extract data lines
        data_lines = lines[data_start:]
        data = [line.split() for line in data_lines if line.strip() and not line.startswith("#")]

        print(f"Loaded {len(data)} rows of data.")  # Debug
        if len(data) == 0:
            raise ValueError("No valid data found in the file.")

        # Define base column names
        base_columns = [
            "Routine Code", "Timestamp", "Routine Count", "Repetition Count",
            "Duration", "Integration Time [ms]", "Number of Cycles", "Saturation Index",
            "Filterwheel 1", "Filterwheel 2", "Zenith Angle [deg]", "Zenith Mode",
            "Azimuth Angle [deg]", "Azimuth Mode", "Processing Index", "Target Distance [m]",
            "Electronics Temp [°C]", "Control Temp [°C]", "Aux Temp [°C]", "Head Sensor Temp [°C]",
            "Head Sensor Humidity [%]", "Head Sensor Pressure [hPa]", "Scale Factor", "Uncertainty Indicator"
        ]

        # Calculate pixel column names for averaged groups of 200
        pixel_columns = [f"Pixel {i}-{i + 199}" for i in range(1, 2001, 200)]

        # Combine base columns and pixel columns
        column_names = base_columns + pixel_columns

        # Create DataFrame
        df = pd.DataFrame(data, dtype=str)

        # Assign dynamic column names
        df.columns = base_columns + list(range(len(base_columns), df.shape[1]))  # Temporarily name remaining columns

        # Convert numeric columns
        numeric_columns = base_columns[2:]
        df[numeric_columns] = df[numeric_columns].apply(pd.to_numeric, errors="coerce")

        # Aggregate pixel columns
        for i, col_name in enumerate(pixel_columns):
            start = 24 + i * 200
            end = start + 200
            df[col_name] = df.iloc[:, start:end].apply(pd.to_numeric, errors="coerce").mean(axis=1)

        # Retain only the base columns and aggregated pixel columns
        df = df[base_columns + pixel_columns]

        # Convert Timestamp column
        df["Timestamp"] = pd.to_datetime(df["Timestamp"], errors="coerce")

        return df

    except Exception as e:
        print(f"Error processing file: {e}")  # Log the error
        return pd.DataFrame()

# App Layout
app.layout = dbc.Container(
    [
        dbc.Row(dbc.Col(html.H1("Pandonia Data Viewer- L0"), className="text-center my-4")),
        dbc.Row(
            dbc.Col(dcc.Dropdown(id="location-dropdown", placeholder="Select Location"), width=6),
            className="mb-4",
            justify="center",
        ),
        dbc.Row(
            dbc.Col(dcc.Dropdown(id="device-dropdown", placeholder="Select Device"), width=6),
            className="mb-4",
            justify="center",
        ),
        dbc.Row(
            dbc.Col(dcc.Dropdown(id="file-dropdown", placeholder="Select File"), width=6),
            className="mb-4",
            justify="center",
        ),
        dbc.Row(
            [
                dbc.Col(
                    [
                        html.Label("Filter by Routine Code"),
                        dcc.Dropdown(id="routine-code-dropdown", options=[], value=None, placeholder="Select Routine Code"),
                    ],
                    width=6,
                ),
                dbc.Col(
                    [
                        html.Label("Select Column for Visualization"),
                        dcc.Dropdown(id="column-dropdown", options=[], value=None, placeholder="Select Column"),
                    ],
                    width=6,
                ),
            ],
            className="mb-4",
        ),
        dbc.Row(dbc.Col(html.Div(id="data-status"), className="text-center"), className="mb-4"),
        dbc.Row(dbc.Col(dcc.Graph(id="line-chart"), width=12), className="mt-4"),
    ],
    fluid=True,
)

@app.callback(
    Output("location-dropdown", "options"),
    Input("location-dropdown", "id"),
)
def populate_locations(_):
    """Populate the location dropdown."""
    locations = list_items(BASE_URL)
    return [{"label": loc, "value": loc} for loc in locations]

@app.callback(
    Output("device-dropdown", "options"),
    Input("location-dropdown", "value"),
)
def update_device_dropdown(selected_location):
    if selected_location:
        devices_url = urljoin(BASE_URL, f"{selected_location}/")
        devices = list_items(devices_url)
        return [{"label": device, "value": device} for device in devices]
    return []

@app.callback(
    Output("file-dropdown", "options"),
    [Input("location-dropdown", "value"), Input("device-dropdown", "value")],
)
def update_file_dropdown(selected_location, selected_device):
    if selected_location and selected_device:
        files_url = urljoin(BASE_URL, f"{selected_location}/{selected_device}/L0/")
        files = list_items(files_url)
        return [{"label": file, "value": urljoin(files_url, file)} for file in files]
    return []

@app.callback(
    [
        Output("routine-code-dropdown", "options"),
        Output("column-dropdown", "options"),
        Output("data-status", "children"),
        Output("line-chart", "figure"),
    ],
    [Input("file-dropdown", "value"), Input("routine-code-dropdown", "value"), Input("column-dropdown", "value")],
)
def load_and_visualize(file_url, selected_routine_code, selected_column):
    if file_url:
        print(f"Fetching file from {file_url}")  # Debug
        file_content = fetch_file(file_url)
        if file_content:
            print(f"Fetched file content size: {len(file_content)} bytes.")  # Debug
            if file_url.endswith(".bz2"):
                file_content = decompress_bz2_file(file_content)
                print(f"Decompressed file content size: {len(file_content)} characters.")  # Debug
            if file_content:
                global uploaded_df
                uploaded_df = process_txt_file(file_content)
                if not uploaded_df.empty:
                    routine_codes = uploaded_df["Routine Code"].unique().tolist()
                    routine_code_options = [{"label": code, "value": code} for code in routine_codes]
                    column_options = [{"label": col, "value": col} for col in uploaded_df.columns if col != "Routine Code"]
                    filtered_df = uploaded_df.copy()
                    if selected_routine_code:
                        filtered_df = filtered_df[filtered_df["Routine Code"] == selected_routine_code]
                    if selected_column:
                        fig = px.line(filtered_df, x="Timestamp", y=selected_column, title=f"{selected_column} Over Time")
                    else:
                        fig = px.line(title="No Column Selected")
                    return routine_code_options, column_options, f"File loaded successfully: {file_url}", fig
    return [], [], "File failed to load", px.line(title="No Data Available")

# Run the App
if __name__ == "__main__":
    app.run_server(debug=True)
