# VISION

**VISION is an AI-Powered Personal Productivity & Knowledge Workspace**, designed to combine task management, personal knowledge, and document intelligence with an agentic workflow.

## Features
- **AI Agent Chat**: Use natural language to create tasks, take notes, and search through your knowledge.
- **Task Management**: Automatically generated and categorized tasks with priorities.
- **RAG Document Pipeline**: Upload PDFs which are extracted, chunked, and embedded into pgvector for semantic search.
- **Semantic Notes**: Notes are embedded with pgvector so the agent natively understands content meaning.
- **Modern UI**: Full-stack Next.js app with shadcn/ui, Tailwind CSS, and Framer Motion animations in a beautiful Glassmorphism Dark mode.

## Tech Stack
- Frontend: Next.js (App Router), React, TailwindCSS, Framer Motion
- Backend: Django, Django REST Framework, Celery, Redis
- Database: PostgreSQL with `pgvector`
- Auth: JWT (JSON Web Tokens)

## Getting Started

### 1. Prerequisites
- Docker & Docker Compose
- Node.js (v18+)
- Python 3.11+
- Redis (Handled via docker-compose)
- PostgreSQL (Handled via docker-compose)

### 2. Backend Setup
1. Launch Postgres (pgvector) and Redis:
   ```bash
   docker-compose up -d
   ```
2. Navigate to `backend` and activate the virtual environment.
   ```bash
   cd backend
   python -m venv env
   # Windows
   .\env\Scripts\Activate.ps1
   # (Or Mac/Linux: source env/bin/activate)
   ```
3. Install dependencies:
   ```bash
   pip install django djangorestframework psycopg2-binary pgvector celery redis python-dotenv djangorestframework-simplejwt django-cors-headers
   ```
4. Run migrations:
   ```bash
   python manage.py migrate
   ```
5. Start the backend server:
   ```bash
   python manage.py runserver
   ```
6. (Optional) Run Celery Worker for Document Background Processing:
   ```bash
   celery -A config worker -l info
   ```

### 3. Frontend Setup
1. Open a new terminal and navigate to `frontend`:
   ```bash
   cd frontend
   ```
2. Install dependencies:
   ```bash
   npm install
   ```
3. Run the development server:
   ```bash
   npm run dev
   ```
4. Access the web app at `http://localhost:3000/login`.

## Architecture Note
This MVP demonstrates a full-stack asynchronous application utilizing pgvector for Semantic Search (RAG) and Django models for structured data tracking representing a personal workspace.
