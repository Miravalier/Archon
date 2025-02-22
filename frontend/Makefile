.PHONY: all
all: build run


.PHONY: build
build:
	yarn
	yarn vite build


.PHONY: run
run:
	docker compose --env-file ../.env up -d


.PHONY: down
down:
	docker compose --env-file ../.env down
