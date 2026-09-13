# Natural Language GIS for Hong Kong Public Facilities

[简体中文](README.md) | English

GeoAI lets users discover public facility data, create maps, and run spatial analyses through conversation. Azure OpenAI interprets requests and calls tools, the Python backend performs spatial calculations, and the frontend displays interactive maps with PNG export.

## Core Features

- **Data access:** built-in facility and district datasets, Excel point uploads, and official CSDI dataset search and download.
- **Spatial analysis:** district counts and density, straight-line buffers, shortest walking/driving network distances and routes, constant-speed driving-time coverage, and cross-dataset facility queries.
- **Interactive mapping:** district choropleths, facility points, multiple layers, and conversational edits to titles, colors, and map elements.
- **Results:** optional tabbed tables, bidirectional map selection, search, sorting, pagination, filtered CSV export, saved-layer restoration, session isolation, data quality checks, and source records.

The **GeoAI chat** panel supports follow-up requests. Tool logs appear under **Operation details**, while Excel and CSDI controls are under **Data sources & uploads**. Result tables start collapsed; maps can be used independently.

## Technology Stack

| Layer | Technologies | Purpose |
|---|---|---|
| Frontend | React, Vite | User interface and frontend builds |
| Mapping | React-Leaflet, Leaflet, MapLibre GL | Interactive maps, layers, and basemap rendering |
| Backend | Python, Flask | APIs, sessions, and tool execution |
| Language model | Azure OpenAI, Function Calling | Request interpretation, tool selection, and parameters |
| Spatial processing | GeoPandas, Shapely | Coordinate transformation, spatial joins, and buffers |
| Network analysis | OSMnx, NetworkX | Network preparation, shortest paths, and accessibility |
| Tabular data | pandas, openpyxl | Excel input, field processing, and validation |

**Sources and APIs:** the official CSDI catalogue and WFS services, the Lands Department Location Search API, built-in facility and district data, and user-uploaded Excel files.

## Quick Start

These instructions use **Windows and PowerShell**. Install Git, Python 3.10+, and Node.js 20.19+ (20.x) or 22.12+, and prepare an Azure OpenAI resource and deployment.

### 1. Get the Project and Install Dependencies

Open PowerShell in the directory where you want to store the project:

```powershell
git clone https://github.com/yicheng-xiang/geoAI.git
cd geoAI\GIS_agent\back_end
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\front_end
npm ci
cd ..\..
```

Alternatively, select **Code → Download ZIP** on GitHub and extract it. Start from the extracted project root, skip the clone command, and replace the second command with `cd GIS_agent\back_end`. Run subsequent commands from the project root; no particular drive or directory is required.

### 2. Configure Credentials

Create a local configuration from the template and open it in Notepad. An existing configuration is not overwritten:

```powershell
if (!(Test-Path GIS_agent\back_end\.env)) {
    Copy-Item GIS_agent\back_end\.env.example GIS_agent\back_end\.env
}
notepad GIS_agent\back_end\.env
```

Keep the variable names unchanged. Enter the **endpoint and full API key** from the same Azure OpenAI resource, then save with **Ctrl+S**:

```env
AZURE_OPENAI_ENDPOINT=https://your-resource.cognitiveservices.azure.com/
AZURE_OPENAI_KEY=your-api-key
```

The filename must be **`.env`, not `.env.txt`**. Store credentials only in the local, Git-ignored `.env`; the repository template contains placeholders. [agent.py](GIS_agent/back_end/agent.py) currently uses deployment name `gpt-5-mini` and API version `2024-12-01-preview`. If your deployment has a different name, update its `model` value. [Configuration details (Chinese)](docs/user-guide.md#详细密钥配置)

### 3. Launch and Create Your First Map

Double-click **start_geoai.bat** in the project root to open the [application](http://localhost:5173/). Try example 1 below.

After generating a map, refine its title or select **Export preview → Download PNG**. Use **stop_geoai.bat** to stop the application. Restart after editing `.env`; restarting clears temporary session data.

### 4. Optional: Prepare Road Networks

**Prepare the cache for each required travel mode before running network analysis.** Ordinary mapping and straight-line buffers do not need it:

```powershell
.\GIS_agent\back_end\.venv\Scripts\python.exe .\GIS_agent\back_end\prepare_road_network.py --mode drive
# Run only if walking-distance analysis is needed.
.\GIS_agent\back_end\.venv\Scripts\python.exe .\GIS_agent\back_end\prepare_road_network.py --mode walk
```

The first run downloads Hong Kong networks and caches them as `.geoai-runtime/networks/hong_kong_drive.graphml` and `hong_kong_walk.graphml`. Later runs reuse the caches by default. Walking queries are currently slow. Network distance uses metres; driving time uses minutes and a scenario speed. They are not interchangeable.

## Example Requests

Copy these requests into the chat. Use separate sessions unless an example specifies a follow-up; clearing a session removes temporary data. Counts depend on the actual dataset snapshot.

| # | Task and prerequisites | Request |
|---|---|---|
| 1 | Categorical district map | `Show all 18 Hong Kong districts, colored by district name using tab20.` |
| 2 | District counts from built-in data | `Count ambulance depots by district using the built-in dataset and map the counts.` |
| 3 | District density from built-in data | `Calculate primary school density per square kilometre by district using the built-in dataset.` |
| 4 | Point overlay; follow example 1 | `Overlay ambulance depot points from the built-in dataset on the current district map. Keep the district layer.` |
| 5 | Presentation-only edit; follow example 2 | `Change the palette to Blues and the title to "Ambulance Depots by District". Keep the analysis unchanged.` |
| 6 | Uploaded-point aggregation; upload an `.xlsx` first | `Count all uploaded points by district and create a choropleth.` |
| 7 | Named-place straight-line buffer; internet required | `Find primary schools within a straight-line distance of 1 km from Hong Kong Polytechnic University Block Z using the built-in dataset.` |
| 8 | Driving coverage; prepare the network first | `Show 10-minute driving coverage FROM Aberdeen Ambulance Depot at 30 km/h using the built-in dataset.` |
| 9 | CSDI discovery, download, and mapping; internet required | `Search CSDI for badminton courts and show their locations in Hong Kong.` |
| 10 | Cross-dataset CSDI buffer; required datasets are downloaded by the tool | `Using CSDI, find ambulance depots within 500 metres of Tung Cheong Street Sports Centre from the public fitness rooms dataset.` |

**Follow-up sequence:** after example 7, send each request separately and wait for completion. Prepare both walking and driving networks first.

1. `Use walking distance instead of straight-line distance. Keep the same origin and 1 km threshold.`
2. `Now use driving distance and increase the threshold to 3 km.`
3. `Include secondary schools too, but only those within the same driving distance. Show the shortest routes to the matched schools.`
4. `Make primary schools red and secondary schools blue. Keep the analysis unchanged.`

Changing the distance, travel mode, or facility categories recalculates the analysis and saves a new result. Title edits and color changes through `restyle_map` do not create another result. Routes are returned shortest-path geometries, not straight lines between points.

For coordinate queries, map elements, dataset refreshes, and cross-dataset driving-time examples, see the [user guide (Chinese)](docs/user-guide.md#分类使用示例).

## Optional Result Tables

Select **Show table** to expand the panel. Each analysis has a tab with independent search, numeric sorting, and pagination (50 rows per page). CSV export includes all filtered records, not just the current page. Selecting a table row or a business feature on the map links the selection, location, and popup in both directions.

Switching tabs does not automatically change the map. If an older result says **Not displayed on map**, select **Show on map** to restore its saved layers without recalculating or downloading. Closing a tab only hides the table; reopen it through **Result list**. Clearing the session or restarting the backend removes these in-memory results. PNG exports exclude the table and temporary selection highlights by default.

## Data and Analysis Scope

- **CSDI:** retrieve the catalogue → filter by keywords → select a dataset → download and validate WFS data → map it. A search result does not guarantee import compatibility. The generic adapter supports single-layer Hong Kong WGS84 point data with identifiable English names, up to 10,000 records. AI dataset recommendations are not implemented.
- **Excel:** the first worksheet of an `.xlsx` file, containing names and WGS84 latitude/longitude coordinates; maximum 5 MB and 10,000 rows. [Fields and analysis details (Chinese)](docs/user-guide.md#本地与-excel-数据)
- **Analysis:** district counts and density accept registered point data, including built-in data, Excel uploads, and downloaded compatible CSDI snapshots. Network distances include facility-to-road access distances. Driving times use constant-speed, directional scenarios, not live traffic or ambulance response times. Population coverage, equity analysis, and arbitrary data formats are not supported.
- **Locations and provenance:** names are resolved through the official API. Low-relevance, ambiguous, or conflicting building-block candidates cannot be used directly as origins. CSDI snapshots remain separate from the local database; a downloaded dataset is not necessarily displayed on the map.

## Troubleshooting

| Problem | Action |
|---|---|
| Page will not open | Check the startup window and `.geoai-runtime/` logs, installed dependencies, and ports 5000/5173. Allow direct proxy bypass for localhost / 127.0.0.1. |
| Authentication failure or deployment not found | Check the `.env` filename, endpoint, key, and deployment name; save and restart. Opening the webpage alone does not validate credentials. |
| Missing walking/driving network | Run the preparation command with `--mode walk` or `--mode drive`, matching the error. |
| `GEOCODING_SERVICE_UNAVAILABLE` | The location API connection failed; this does not mean zero facilities. Retry later or provide verified WGS84 coordinates. No port change is needed. The current default timeout is 10 seconds, with no automatic retry; successful locations are cached in memory only. |
| `LOCATION_CONFIRMATION_REQUIRED` | Use an exact suggested official name or verified coordinates. Do not assume a fuzzy suggestion is the intended location. A failed request retains the last successful map, not a newly completed analysis. |
| CSDI timeout or incompatible data | Retry network timeouts. Multi-layer services, line/polygon data, or unsupported fields need additional adapters. A failed refresh retains the previous snapshot. |
| Data disappears after restart | Excel data, CSDI snapshots, and conversations are stored in session memory and must be reimported after restart. Rerun analyses after refreshing datasets. |

## Project Structure and Development

```text
GIS_agent/
├── back_end/       # Flask, AI orchestration, GIS tools, and backend tests
├── front_end/      # React UI, maps, PNG export, and frontend tests
└── data/           # Built-in district and facility data
docs/              # User guide, development notes, and acceptance records
start_geoai.bat     # Start the application
stop_geoai.bat      # Stop the application
```

[Development APIs and test commands (Chinese)](docs/development.md) · [CSDI acceptance record (Chinese)](docs/csdi-stability-report-2026-09-07.md)

**Stage acceptance, 2026-09-11: all 120 backend tests and 28 frontend tests passed, together with lint and the production build.** Twelve conversations comprising 60 turns were exercised using the real model and GIS tools, followed by major defect fixes and targeted retests. Browser checks verified map replacement, recoloring, historical-result restoration, and map–table interaction. This release excludes the new test set and detailed acceptance report. Official services remain intermittently unavailable, and full PNG export acceptance remains to be completed.
