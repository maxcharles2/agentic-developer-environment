.PHONY: dev build test lint migrate proto clean logs restart

# Start all services with live rebuild
dev:
	docker compose up --build

# Build all Docker images without starting
build:
	docker compose build

# Run tests across all services
test:
	docker compose run --rm orchestrator pytest services/orchestrator/tests
	docker compose run --rm context pytest services/context/tests
	docker compose run --rm sandbox pytest services/sandbox/tests
	docker compose exec gateway npx vitest run

# Lint all services
lint:
	docker compose run --rm orchestrator ruff check services/orchestrator
	docker compose run --rm context ruff check services/context
	docker compose run --rm sandbox ruff check services/sandbox
	docker compose exec gateway npx eslint services/gateway/src

# Apply all SQL migrations against the running supabase-db container
migrate:
	@for f in infra/supabase/migrations/*.sql; do \
		echo "Applying $$f..."; \
		docker compose exec -T supabase-db psql -U postgres -f /dev/stdin < "$$f"; \
	done

# Generate gRPC stubs from .proto definitions
proto:
	cd packages/proto && buf generate

# Remove all containers, networks, and named volumes
clean:
	docker compose down -v --remove-orphans

# Stream logs from all services
logs:
	docker compose logs -f

# Restart all running services
restart:
	docker compose restart
