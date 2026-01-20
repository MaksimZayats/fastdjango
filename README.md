# Fast Django

Production-ready **FastAPI** template with **Django ORM**, admin panel, and **Celery** background tasks —
featuring dependency injection, type-safe configuration, and comprehensive observability.

## Features

- **HTTP API** — [FastAPI](https://fastapi.tiangolo.com/) with automatic OpenAPI documentation
- **Background Tasks** — [Celery](https://docs.celeryq.dev/en/stable/) with beat scheduler
- **Dependency Injection** — [punq](https://github.com/bobthemighty/punq) IoC container
- **Type-Safe Config** — [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) with
  validation
- **Observability** — [Logfire](https://logfire.pydantic.dev/docs/) (OpenTelemetry) integration
- **Production Ready** — Docker Compose with PostgreSQL, PgBouncer, Redis, MinIO

## At a Glance

**Define a service** with business logic and database operations:

```python
# src/core/todo/services.py
from django.db import transaction
from core.todo.models import Todo

class TodoService:
    def get_todo_by_id(self, todo_id: int) -> Todo | None:
        return Todo.objects.filter(id=todo_id).first()

    def list_todos(self, user_id: int) -> list[Todo]:
        return list(Todo.objects.filter(user_id=user_id))

    @transaction.atomic
    def create_todo(self, user_id: int, title: str) -> Todo:
        return Todo.objects.create(user_id=user_id, title=title)
```

**Create a controller** — services are auto-injected via the IoC container:

```python
# src/delivery/http/todo/controllers.py
from dataclasses import dataclass
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.todo.services import TodoService
from delivery.http.auth.jwt import AuthenticatedRequest, JWTAuth, JWTAuthFactory
from infrastructure.delivery.controllers import Controller

class TodoSchema(BaseModel):
    id: int
    title: str
    completed: bool

@dataclass
class TodoController(Controller):
    _jwt_auth_factory: JWTAuthFactory
    _todo_service: TodoService  # Auto-injected

    def register(self, registry: APIRouter) -> None:
        registry.add_api_route(
            path="/v1/todos",
            endpoint=self.list_todos,
            methods=["GET"],
            dependencies=[Depends(self._jwt_auth_factory())],
        )

    def list_todos(self, request: AuthenticatedRequest) -> list[TodoSchema]:
        todos = self._todo_service.list_todos(user_id=request.state.user.id)
        return [TodoSchema.model_validate(t, from_attributes=True) for t in todos]
```

> **The Golden Rule:** Controllers never access models directly → all database operations go through services.

## Prerequisites

Before getting started, ensure you have installed:

- **uv** — Blazingly fast Python package manager ([Install uv](https://docs.astral.sh/uv/getting-started/installation/))
- **Docker & Docker Compose** — For infrastructure
  services ([Install Docker](https://docs.docker.com/get-started/get-docker/))

## Quick Start

### 1. Clone the Repository

```bash
git clone https://github.com/MaksimZayats/fastdjango.git
cd fastdjango
```

### 2. Rename the Project

Replace the default project name in `pyproject.toml` with your own.
Use lowercase letters, numbers, and hyphens (e.g., `my-awesome-api`, `backend-service`).

### 3. Install Dependencies

```bash
uv sync --locked --all-extras --dev
```

### 4. Configure Environment

```bash
cp .env.example .env
```

The `.env.example` contains sensible defaults for local development. Key variables:

- `DJANGO_SECRET_KEY` — Django secret key
- `JWT_SECRET_KEY` — JWT signing key
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis connection string

### 5. Start Infrastructure Services

```bash
docker compose up -d postgres redis minio
```

This starts:

- **PostgreSQL 18** — Primary database
- **PgBouncer** — Connection pooling (transaction mode)
- **Redis** — Cache and Celery broker
- **MinIO** — S3-compatible object storage

### 6. Initialize Database and Storage

```bash
docker compose up minio-create-buckets migrations collectstatic
```

This runs one-time setup tasks:

1. Creates MinIO buckets for static/media files
2. Applies Django database migrations
3. Collects static files to MinIO

### 7. Start Development Server

```bash
make dev
```

The API is available at `http://localhost:8000` with interactive docs at `/docs`.

## Verify Installation

```bash
curl http://localhost:8000/v1/health
```

Expected response:

```json
{
  "status": "ok"
}
```

## Documentation

Full documentation is available at [fastdjango.zayats.dev](https://fastdjango.zayats.dev).

| Section                                                                                         | Description                                |
|-------------------------------------------------------------------------------------------------|--------------------------------------------|
| [Quick Start](https://fastdjango.zayats.dev/getting-started/quick-start/)                         | Get running in 5 minutes                   |
| [Project Structure](https://fastdjango.zayats.dev/getting-started/project-structure/)             | Understand the codebase organization       |
| [Development Environment](https://fastdjango.zayats.dev/getting-started/development-environment/) | IDE setup and tooling                      |
| [Tutorial: Build a Todo List](https://fastdjango.zayats.dev/tutorial/)                            | Learn by building a complete feature       |
| [Concepts](https://fastdjango.zayats.dev/concepts/)                                               | Service layer, IoC, controllers, factories |
| [How-To Guides](https://fastdjango.zayats.dev/how-to/)                                            | Add domains, tasks, secure endpoints       |
| [Reference](https://fastdjango.zayats.dev/reference/)                                             | Environment variables, Makefile, Docker    |

## Tech Stack

| Component       | Technology        | Documentation                                                                              |
|-----------------|-------------------|--------------------------------------------------------------------------------------------|
| HTTP API        | FastAPI 0.128+    | [fastapi.tiangolo.com](https://fastapi.tiangolo.com/)                                      |
| ORM & Admin     | Django 6+         | [docs.djangoproject.com](https://docs.djangoproject.com/en/stable/)                        |
| Task Queue      | Celery 5.x        | [docs.celeryq.dev](https://docs.celeryq.dev/en/stable/)                                    |
| Validation      | Pydantic 2.x      | [docs.pydantic.dev](https://docs.pydantic.dev/latest/)                                     |
| Settings        | Pydantic Settings | [docs.pydantic.dev/settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| IoC Container   | punq              | [github.com/bobthemighty/punq](https://github.com/bobthemighty/punq)                       |
| Observability   | Logfire           | [Logfire docs](https://logfire.pydantic.dev/docs/)                                         |
| Package Manager | uv                | [docs.astral.sh/uv](https://docs.astral.sh/uv/)                                            |

## License

[MIT](LICENSE.md)
