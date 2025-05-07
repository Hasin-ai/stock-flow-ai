# Installation Guide

## Setup Process

### Backend Setup

1.  Navigate to the backend folder:

-   cd backend

2.  Install required dependencies:

-   pip install -r requirements.txt

3.  Configure environment variables:

    -   Create a `.env` file in the backend directory
        -   Here setup alphavantage api
        -   Example:

> ![](./image1.png){width="5.459095581802274in"
> height="1.2085017497812773in"}

-   Create a config.py in backend/app directory
    -   Here setup gemini api
    -   Example

> ![](./image2.png){width="3.9172134733158357in"
> height="4.042230971128609in"}

-   Add your database connection details

### Qdrant Database Setup

1.  Run Qdrant database using Docker:

-   docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant

2.  Update your `.env` file with the Qdrant port configuration

### Launch the Application

1.  Start the backend server:

-   - cd backend

        - python –m venv venv

        - .\vevn\Scripts\activate

        -   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

    The backend will run on `localhost:8080`

2.  Start the frontend:

-   Simply run the frontend through vscode live server

    The frontend will be available at `localhost:5050`

## Verification

-   Backend API: http://localhost:8080
-   Frontend interface: http://localhost:5050
