import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import numpy as np
from datetime import datetime, timedelta
import time

# Page config
st.set_page_config(
    page_title="BGS Sensor Explorer", 
    page_icon="🌍", 
    layout="wide",
    initial_sidebar_state="expanded"
)

# API base URL
BASE_URL = "https://sensors.bgs.ac.uk/FROST-Server/v1.1"

# Cache API calls for better performance
@st.cache_data(ttl=300)  # 5-minute cache
def get_sensors(limit=1000, filter_text=None):
    """Get list of sensors"""
    url = f"{BASE_URL}/Things"
    params = {}
    if limit:
        params["$top"] = limit
    if filter_text:
        params["$filter"] = filter_text
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching sensors: {e}")
        return {"value": []}

@st.cache_data(ttl=300)
def get_sensor_details(sensor_id):
    """Get detailed information about a sensor"""
    url = f"{BASE_URL}/Things({sensor_id})"
    params = {"$expand": "Datastreams,Locations"}
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching sensor details: {e}")
        return {}

@st.cache_data(ttl=60)  # 1-minute cache for observations
def get_observations(datastream_id, limit=100, time_filter=None):
    """Get observations from a datastream"""
    url = f"{BASE_URL}/Datastreams({datastream_id})/Observations"
    params = {
        "$top": limit,
        "$orderby": "phenomenonTime desc"
    }
    if time_filter:
        params["$filter"] = time_filter
    
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error fetching observations: {e}")
        return {"value": []}

def format_datastream_info(datastream):
    """Format datastream information for display"""
    return {
        "ID": datastream.get("@iot.id"),
        "Name": datastream.get("name", ""),
        "Description": datastream.get("description", ""),
        "Unit": datastream.get("unitOfMeasurement", {}).get("symbol", ""),
        "Property": datastream.get("observedProperty", {}).get("name", "")
    }

def create_time_series_plot(df, title, y_label, unit):
    """Create a time series plot"""
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df['time'],
        y=df['result'],
        mode='lines+markers',
        name=f'{y_label} ({unit})',
        line=dict(width=2),
        marker=dict(size=4)
    ))
    
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=f"{y_label} ({unit})",
        hovermode='x unified',
        template="plotly_white"
    )
    
    return fig

def create_comparison_plot(data_dict, title):
    """Create a comparison plot for multiple datastreams"""
    fig = make_subplots(
        rows=len(data_dict), 
        cols=1,
        subplot_titles=list(data_dict.keys()),
        shared_xaxes=True,
        vertical_spacing=0.1
    )
    
    colors = px.colors.qualitative.Set3
    
    for i, (name, data) in enumerate(data_dict.items(), 1):
        if not data['df'].empty:
            fig.add_trace(
                go.Scatter(
                    x=data['df']['time'],
                    y=data['df']['result'],
                    mode='lines+markers',
                    name=f"{name} ({data['unit']})",
                    line=dict(color=colors[i-1], width=2),
                    marker=dict(size=3)
                ),
                row=i, col=1
            )
            
            fig.update_yaxes(title_text=f"{name} ({data['unit']})", row=i, col=1)
    
    fig.update_layout(
        title=title,
        height=200 * len(data_dict),
        template="plotly_white",
        showlegend=False
    )
    
    return fig

# Main app
# st.title("🌍 BGS Sensor Data Explorer")
# st.markdown("Interactive exploration of the British Geological Survey sensor network")

# Sidebar
st.sidebar.header("BGS Sensor Data Explorer")

# Remove the sensor limit slider and use a fixed large number or None
with st.spinner("Loading sensors..."):
    sensors_data = get_sensors(limit=1000)  # Use a large number to get all sensors

if not sensors_data.get("value"):
    st.error("No sensors found. Please check your connection.")
    st.stop()

sensors = sensors_data["value"]

# Create sensor options
sensor_options = {}
for sensor in sensors:
    sensor_id = sensor.get("@iot.id")
    sensor_name = sensor.get("name", f"Sensor {sensor_id}")
    sensor_description = sensor.get("description", "")
    display_name = f"{sensor_name}"
    if sensor_description:
        display_name += f" - {sensor_description[:50]}..."
    sensor_options[display_name] = sensor_id

# Sensor selection
selected_sensor_name = st.sidebar.selectbox(
    "Select a sensor:",
    options=list(sensor_options.keys()),
    help="Choose a sensor to explore its datastreams"
)

selected_sensor_id = sensor_options[selected_sensor_name]

# Load sensor details
with st.spinner("Loading sensor details..."):
    sensor_details = get_sensor_details(selected_sensor_id)

if not sensor_details:
    st.error("Could not load sensor details.")
    st.stop()

# SENSOR INFORMATION SECTION (COMPACT - MOVED BACK TO TOP)
st.header(f"{sensor_details.get('name', 'Unknown Sensor')}")

# Add description directly under header
description = sensor_details.get('description', '')
if description:
    st.write(description)

# Compact sensor info in expandable sections
with st.expander("ℹ️ Sensor Details", expanded=False):
    col1, col2 = st.columns(2)
    
    with col1:
        st.write(f"**ID:** {sensor_details.get('@iot.id')}")
        st.write(f"**Name:** {sensor_details.get('name', 'N/A')}")
        
        # Location info
        locations = sensor_details.get("Locations", [])
        if locations:
            location = locations[0]
            coords = location.get("location", {}).get("coordinates", [])
            if coords and len(coords) >= 2:
                st.write(f"**Coordinates:** [{coords[0]:.6f}, {coords[1]:.6f}]")
    
    with col2:
        # Key properties only
        properties = sensor_details.get("properties", {})
        if properties:
            key_props = ["category", "borehole_reference", "observation_start_date"]
            for key in key_props:
                if key in properties:
                    st.write(f"**{key.replace('_', ' ').title()}:** {properties[key]}")
    
    # Description
    description = sensor_details.get('description', 'N/A')
    if description != 'N/A':
        st.write(f"**Description:** {description}")
    
    # Simple map
    if locations and coords and len(coords) >= 2:
        map_data = pd.DataFrame({
            'lat': [coords[1]],
            'lon': [coords[0]]
        })
        st.map(map_data, zoom=10)

# Prepare datastreams and time settings first
datastreams = sensor_details.get("Datastreams", [])

if not datastreams:
    st.warning("No datastreams found for this sensor.")
    st.stop()

# Create datastream selection
datastream_options = {}
datastream_info = {}

for ds in datastreams:
    ds_id = ds.get("@iot.id")
    ds_name = ds.get("name", f"Datastream {ds_id}")
    unit = ds.get("unitOfMeasurement", {}).get("symbol", "")
    display_name = f"{ds_name}"
    if unit:
        display_name += f" ({unit})"
    
    datastream_options[display_name] = ds_id
    datastream_info[ds_id] = format_datastream_info(ds)

# Time range selection
time_range = st.sidebar.selectbox(
    "Select time range:",
    ["All available", "Last 24 hours", "Last 7 days", "Last 30 days", "Last 90 days"],
    help="Choose the time period for data retrieval"
)

# Convert time range to filter
time_filter = None
if time_range != "All available":
    hours_map = {
        "Last 24 hours": 24,
        "Last 7 days": 24 * 7,
        "Last 30 days": 24 * 30,
        "Last 90 days": 24 * 90
    }
    hours = hours_map[time_range]
    start_time = datetime.utcnow() - timedelta(hours=hours)
    time_filter = f"phenomenonTime ge {start_time.strftime('%Y-%m-%dT%H:%M:%SZ')}"

# Number of observations
obs_limit = st.sidebar.slider("Max observations per datastream", 50, 1000, 200)

# Available datastreams in expandable section
with st.expander("📊 Available Datastreams", expanded=False):
    df_datastreams = pd.DataFrame([info for info in datastream_info.values()])
    st.dataframe(df_datastreams, use_container_width=True)

# DATA VISUALIZATION SECTION
st.header("Data Visualisation")

# Data visualization mode selection
if len(datastream_options) > 1:
    viz_mode = st.radio(
        "",  # Removed the label text
        ["Single Datastream", "Compare Multiple Datastreams"],
        horizontal=True
    )
else:
    viz_mode = "Single Datastream"

if viz_mode == "Single Datastream":
    # Single datastream analysis
    st.subheader("Single Datastream Analysis")
    selected_datastream = st.selectbox(
        "Select a datastream to visualize:",
        options=list(datastream_options.keys())
    )

    if selected_datastream:
        datastream_id = datastream_options[selected_datastream]
        
        with st.spinner("Loading observations..."):
            obs_data = get_observations(datastream_id, limit=obs_limit, time_filter=time_filter)
        
        observations = obs_data.get("value", [])
        
        if observations:
            # Convert to DataFrame
            df = pd.DataFrame(observations)
            df['time'] = pd.to_datetime(df['phenomenonTime'])
            df = df.sort_values('time')
            
            # Get unit information
            ds_info = datastream_info[datastream_id]
            unit = ds_info.get("Unit", "")
            property_name = ds_info.get("Property", ds_info.get("Name", ""))
            
            # Statistics
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("📊 Total Points", len(df))
            with col2:
                st.metric("📈 Latest Value", f"{df['result'].iloc[0]:.2f} {unit}")
            with col3:
                st.metric("📉 Min Value", f"{df['result'].min():.2f} {unit}")
            with col4:
                st.metric("📊 Max Value", f"{df['result'].max():.2f} {unit}")
            
            # Time series plot
            fig = create_time_series_plot(
                df, 
                f"{selected_datastream} - Time Series",
                property_name,
                unit
            )
            st.plotly_chart(fig, use_container_width=True, key=f"single_chart_{datastream_id}")
            
            # Data table
            if st.checkbox("Show raw data", key=f"show_raw_data_{datastream_id}"):
                st.dataframe(df[['time', 'result']].head(100), use_container_width=True)
        
        else:
            st.warning(f"No observations found for {selected_datastream} in the selected time range.")

else:  # Compare Multiple Datastreams mode
    # Multi-datastream comparison
    st.subheader("Multi-Datastream Comparison")
    selected_multiple = st.multiselect(
        "Select multiple datastreams to compare:",
        options=list(datastream_options.keys()),
        max_selections=4,
        help="Select up to 4 datastreams for comparison"
    )
    
    if len(selected_multiple) > 1:
        comparison_data = {}
        
        with st.spinner("Loading comparison data..."):
            for ds_name in selected_multiple:
                ds_id = datastream_options[ds_name]
                obs_data = get_observations(ds_id, limit=obs_limit, time_filter=time_filter)
                observations = obs_data.get("value", [])
                
                if observations:
                    df = pd.DataFrame(observations)
                    df['time'] = pd.to_datetime(df['phenomenonTime'])
                    df = df.sort_values('time')
                    
                    ds_info = datastream_info[ds_id]
                    comparison_data[ds_name] = {
                        'df': df,
                        'unit': ds_info.get("Unit", ""),
                        'property': ds_info.get("Property", ds_info.get("Name", ""))
                    }
        
        if comparison_data:
            fig = create_comparison_plot(comparison_data, "Multi-Datastream Comparison")
            st.plotly_chart(fig, use_container_width=True, key="comparison_chart")
        else:
            st.warning("No data available for the selected datastreams.")
    
    elif len(selected_multiple) == 1:
        st.info("Select at least 2 datastreams to see a comparison chart.")
    else:
        st.info("Select 2 or more datastreams from the list above to compare them side by side.")

# (This section has been moved to the top after sensor details)

# (This section is now moved to after data visualization section)

# if selected_datastream:
#     datastream_id = datastream_options[selected_datastream]
    
#     with st.spinner("Loading observations..."):
#         obs_data = get_observations(datastream_id, limit=obs_limit, time_filter=time_filter)
    
#     observations = obs_data.get("value", [])
    
#     if observations:
#         # Convert to DataFrame
#         df = pd.DataFrame(observations)
#         df['time'] = pd.to_datetime(df['phenomenonTime'])
#         df = df.sort_values('time')
        
#         # Get unit information
#         ds_info = datastream_info[datastream_id]
#         unit = ds_info.get("Unit", "")
#         property_name = ds_info.get("Property", ds_info.get("Name", ""))
        
#         # Statistics
#         col1, col2, col3, col4 = st.columns(4)
#         with col1:
#             st.metric("📊 Total Points", len(df))
#         with col2:
#             st.metric("📈 Latest Value", f"{df['result'].iloc[0]:.2f} {unit}")
#         with col3:
#             st.metric("📉 Min Value", f"{df['result'].min():.2f} {unit}")
#         with col4:
#             st.metric("📊 Max Value", f"{df['result'].max():.2f} {unit}")
        
#         # Time series plot
#         fig = create_time_series_plot(
#             df, 
#             f"{selected_datastream} - Time Series",
#             property_name,
#             unit
#         )
#         st.plotly_chart(fig, use_container_width=True)
        
#         # Data table
#         if st.checkbox("Show raw data"):
#             st.dataframe(df[['time', 'result']].head(100), use_container_width=True)
    
#     else:
#         st.warning(f"No observations found for {selected_datastream} in the selected time range.")

# (This section is now moved to after data visualization section)

# Footer
st.markdown("---")
st.markdown("""
**BGS Sensor Explorer** | Data from [British Geological Survey](https://www.bgs.ac.uk/)  
🔗 API: https://sensors.bgs.ac.uk/FROST-Server/v1.1  
⚡ Built with Streamlit
""")

# Add refresh button
if st.sidebar.button("🔄 Refresh Data"):
    st.cache_data.clear()
    st.rerun()