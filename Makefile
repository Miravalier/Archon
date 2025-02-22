.PHONY: all
all: frontend backend


.PHONY: frontend
frontend:
	cd frontend && make all


.PHONY: backend
backend:
	cd backend && make all


.PHONY: down
down:
	cd frontend && make down
	cd backend && make down
