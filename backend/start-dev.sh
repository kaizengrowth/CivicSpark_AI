#!/bin/bash
# Development startup script
# This script sets up the development environment and starts the server

echo "🔧 Starting CivicSpark AI in Development Mode"

# Set environment variable to use development config
export ENV_FILE=".env.development"

# Activate virtual environment
source venv/bin/activate

# Start the development server
echo "🚀 Starting backend server on port 8000..."
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
