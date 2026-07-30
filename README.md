
# NEW-Business-Intelligence-Agent----->Fixed: Switched AI backend from Gemini to Groq (Llama 3.3 70B) for faster, more reliable free-tier access.
📊 BI Agent

## Overview

Founder BI Agent is an AI-powered Business Intelligence application built with **Python** and **Streamlit** that helps founders and executives analyze business data stored in **monday.com**. Instead of manually checking multiple boards, users can ask business questions in natural language and receive summarized insights.

---

## How the Project Works

### 1. Fetch Data from monday.com

The application connects to monday.com using the **monday.com GraphQL API**.

It retrieves data from two boards:

* **Deals Board** – Sales pipeline information
* **Work Orders Board** – Project execution and billing information

The API token is stored securely as an environment variable.

---

### 2. Clean and Normalize Data

The retrieved data is cleaned before analysis.

The application:

* Removes invalid or duplicate rows
* Converts text into numbers and dates
* Handles missing values safely
* Standardizes sector names
* Creates data quality flags
* Normalizes deal names for joining both boards

This ensures consistent and reliable analysis.

---

### 3. Generate Business Aggregates

Instead of calculating values during every question, the application precomputes important business metrics such as:

* Open pipeline by sector
* Deal stage summary
* Win rate by sector
* Upcoming deals
* Work order financial summary
* Execution status
* At-risk work orders

These aggregates provide accurate and fast responses.

---

### 4. AI-Powered Business Analysis

The application uses the **Groq API** (running **Llama 3.3 70B Versatile**) as the Large Language Model (LLM).

The AI receives:

* User question
* Conversation history
* Precomputed business summaries
* Data quality information

Instead of directly accessing the database, the model analyzes the prepared business context and generates clear, executive-level insights.

This approach improves speed, accuracy, and reduces incorrect calculations.

---

### 5. Streamlit User Interface

The Streamlit application provides:

* monday.com data loading
* Business health dashboard
* Leadership summary generation
* Natural language chat interface
* Data quality monitoring

Users simply ask questions like:

> "How is our pipeline looking for the energy sector this quarter?"

The application analyzes the available business data and returns an executive-friendly response.

---

# Why Groq API?

Groq was selected because it provides:

* Natural language understanding
* Business reasoning
* Executive-style summaries
* Easy integration with Python (OpenAI-compatible chat completions interface)
* Very fast inference speed (Groq's LPU hardware significantly outpaces typical API response times)
* Free tier during development, no credit card required

The project is designed so that the AI provider can be replaced with another model (such as OpenAI, Gemini, or Ollama) with minimal changes, while the rest of the application remains the same.

---

# Note

The current project uses the **Groq API** for AI responses.

During testing, the application may display authentication or quota errors if the free Groq API limit is exceeded. This does **not** affect the monday.com integration, data cleaning, or business analytics components. Replacing the API key or switching to another supported LLM restores the AI functionality without changing the overall architecture.

## Problem

My aggregation and normalization logic expected the original CSV column names:

Deal Name
Deal name masked

Since those columns were missing, pandas raised:

KeyError: 'Deal Name'

## Solution

While fetching data from monday.com, I explicitly mapped the primary item name back to the original CSV column names.

```python
row["Name"] = item["name"]

if "deal" in board_name:
    row["Deal Name"] = row["Name"]

if "work" in board_name:
    row["Deal name masked"] = row["Name"]
```

This maintains compatibility with the rest of the application without modifying the aggregation or normalization logic.

# ⚙️ Configuration

Before running the project, create a `.env` file in the project root and add the following environment variables:

```env
GROQ_API_KEY=your_groq_api_key
MONDAY_API_TOKEN=your_monday_api_token
MONDAY_DEALS_BOARD_ID=5030219340
MONDAY_WORK_ORDERS_BOARD_ID=5030218479
```

> **Important:** Replace `your_groq_api_key` and `your_monday_api_token` with your own API keys before running the application.

---

# 🔑 Generating a New Groq API Key

If the application displays errors such as:

- `401 Invalid API Key`
- `429 Rate limit / quota exceeded`

you may need to generate a new Groq API key.

## Steps

1. Visit **Groq Console**:
   https://console.groq.com/keys

2. Sign in with your Google account (or email).

3. Click **Create API Key**.

4. Copy the generated API key (it will look similar to):

```text
gsk_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

5. Open your `.env` file.

6. Replace:

```env
GROQ_API_KEY=your_groq_api_key
```

with your newly generated key:

```env
GROQ_API_KEY=gsk_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
```

7. Save the file.

8. Restart the Streamlit application.

The AI chat functionality should now work correctly, provided your API key has available quota.

## Notes

- Do **not** commit your `.env` file or API keys to GitHub.
- If the free Groq API quota is exhausted, create a new API key or check Groq's current rate limit tiers.
- The rest of the application (monday.com integration, data cleaning, analytics, and dashboard) will continue to work independently of the AI service.

# Technologies Used

* Python
* Streamlit
* Pandas
* monday.com GraphQL API
* Groq API (Llama 3.3 70B Versatile)
* RapidFuzz
* Requests

BI-Agent/
│── app.py
│── agent.py
│── monday_client.py
│── normalize.py
│── aggregates.py
│── requirements.txt
│── README.md
│── .env.example

# 🚀 Installation

1. Clone the repository

```bash
git clone https://github.com/reyya20/BI-Agent.git
cd BI-Agent
```

2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Create a `.env` file

```env
GROQ_API_KEY=your_groq_api_key
MONDAY_API_TOKEN=your_monday_api_token
MONDAY_DEALS_BOARD_ID=5030219340
MONDAY_WORK_ORDERS_BOARD_ID=5030218479
```

4. Run the application

```bash
streamlit run app.py
```

# Project Flow

```text
monday.com Boards
        │
        ▼
Fetch Data using GraphQL API
        │
        ▼
Data Cleaning & Normalization
        │
        ▼
Business Aggregations
        │
        ▼
Build AI Context
        │
        ▼
Groq API (Llama 3.3 70B Versatile)
        │
        ▼
Executive Business Insights
        │
        ▼
Streamlit Dashboard
```

## Features

✅ Live monday.com integration

✅ Data normalization and cleaning

✅ AI-powered founder insights

✅ Leadership summary generation

✅ Cross-board business analysis

✅ Natural language querying

✅ Graceful handling of missing data
