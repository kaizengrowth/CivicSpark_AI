#!/bin/bash
# Complete Development Startup Script
# This script activates the virtual environment and starts both backend and frontend

set -e  # Exit on error

echo "Starting CivicSpark AI Development Environment..."
echo "=================================================="

# Navigate to project root
cd "$(dirname "$0")/.."

# Kill any existing processes on our ports
echo "Cleaning up existing processes..."
lsof -ti :8000 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti :3003 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti :3004 2>/dev/null | xargs kill -9 2>/dev/null || true

# Activate virtual environment
echo "Activating virtual environment..."
if [[ ! -f "backend/venv/bin/activate" ]]; then
    echo "Virtual environment not found. Creating it..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
else
    source backend/venv/bin/activate
fi

echo "Virtual environment active: $(which python)"

# Set environment variables
export PYTHONPATH="${PYTHONPATH}:$(pwd)/backend"
export NODE_ENV=development
# Point backend to Docker Postgres (dev)
export DATABASE_URL="postgresql://user:password@localhost:5432/civicspark_db"

# Create .env if it doesn't exist
if [[ ! -f "backend/.env" ]]; then
    echo "Creating backend .env file..."
    ./scripts/setup_dev_environment.sh
fi

# Clear frontend caches
echo "Clearing frontend caches..."
rm -rf frontend/node_modules/.vite frontend/dist 2>/dev/null || true

echo ""
echo "Starting Services..."
echo "======================="

# Function to start backend
start_backend() {
    echo "Starting Backend (Port 8000)..."
    cd backend
    python -m app.main > ../logs/backend.log 2>&1 &
    BACKEND_PID=$!
    echo "Backend PID: $BACKEND_PID"
    cd ..
}

# Function to start frontend
start_frontend() {
    echo "Starting Frontend (Port 3003/3004)..."
    cd frontend

    # Install dependencies if needed
    if [[ ! -d "node_modules" ]]; then
        echo "Installing frontend dependencies..."
        npm install
    fi

    # Start development server
    npm run dev > ../logs/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "Frontend PID: $FRONTEND_PID"
    cd ..
}

# Create logs directory
mkdir -p logs

# Start Docker services (Postgres + Redis)
echo "Starting Docker services (Postgres + Redis)..."
docker-compose up -d postgres redis

# Wait for database
echo "Waiting for database to be ready..."
sleep 5

# Run database migrations
echo "Running database migrations..."
cd backend
python -m alembic upgrade head
cd ..

# Start backend
start_backend

# Start frontend
start_frontend

echo ""
echo "Development environment started successfully!"
echo "============================================="
echo ""
echo "Access Points:"
echo "- Backend API: http://localhost:8000"
echo "- API Docs: http://localhost:8000/docs"
echo "- Frontend: http://localhost:3003"
echo ""
echo "Logs:"
echo "- Backend: tail -f logs/backend.log"
echo "- Frontend: tail -f logs/frontend.log"
echo ""
echo "To stop all services:"
echo "- Press Ctrl+C to stop this script"
echo "- Run: docker-compose down"
echo ""

# Store PIDs for cleanup
echo $BACKEND_PID > logs/backend.pid
echo $FRONTEND_PID > logs/frontend.pid

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "Shutting down development environment..."

    # Kill backend and frontend processes
    if [[ -f "logs/backend.pid" ]]; then
        BACKEND_PID=$(cat logs/backend.pid)
        kill $BACKEND_PID 2>/dev/null || true
        rm -f logs/backend.pid
    fi

    if [[ -f "logs/frontend.pid" ]]; then
        FRONTEND_PID=$(cat logs/frontend.pid)
        kill $FRONTEND_PID 2>/dev/null || true
        rm -f logs/frontend.pid
    fi

    # Stop Docker services
    docker-compose stop postgres redis

    echo "Development environment stopped."
    exit 0
}

# Set up cleanup on script termination
trap cleanup INT TERM

# Keep script running and show real-time logs
echo "Press Ctrl+C to stop all services"
echo ""

# Wait for both processes
wait
