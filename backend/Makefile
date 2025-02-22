.PHONY: all
all: build run


.PHONY: build
build:
	docker compose --env-file ../.env build


.PHONY: run
run:
	docker compose --env-file ../.env down
	docker compose --env-file ../.env up -d


.PHONY: down
down:
	docker compose --env-file ../.env down
