.PHONY: all
all: network backend frontend


.PHONY: network
network:
	docker network create archon --subnet=10.247.92.0/24 2>/dev/null || true


.PHONY: frontend
frontend: network
	cd frontend && make all


.PHONY: backend
backend: network
	cd backend && make all


.PHONY: down
down:
	cd frontend && make down
	cd backend && make down
	docker network rm archon
