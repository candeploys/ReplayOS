.PHONY: test e2e check doctor run run-bg stop status seed ask list-connectors sync-connectors capture-daemon backup restore migrate vacuum service-install service-uninstall service-status zip docker-build docker-up docker-down

test:
	python3 -m unittest discover -s tests -v

e2e:
	python3 tests/e2e_smoke.py

check:
	python3 -m replayos.cli --config config/replayos.toml --env .env check

doctor:
	python3 -m replayos.cli --config config/replayos.toml --env .env doctor

run:
	python3 -m replayos.cli --config config/replayos.toml --env .env run

run-bg:
	python3 -m replayos.cli --config config/replayos.toml --env .env run-bg

stop:
	python3 -m replayos.cli --config config/replayos.toml --env .env stop

status:
	python3 -m replayos.cli --config config/replayos.toml --env .env status

seed:
	python3 -m replayos.cli --config config/replayos.toml --env .env seed-demo --count 10

ask:
	python3 -m replayos.cli --config config/replayos.toml --env .env ask "Summarize my timeline briefly"

list-connectors:
	python3 -m replayos.cli --config config/replayos.toml --env .env list-connectors

sync-connectors:
	python3 -m replayos.cli --config config/replayos.toml --env .env sync-connectors --limit 20

capture-daemon:
	python3 -m replayos.cli --config config/replayos.toml --env .env capture-daemon --interval 20

backup:
	python3 -m replayos.cli --config config/replayos.toml --env .env backup-db

restore:
	@echo "Usage: make restore INPUT=backups/replayos-XXXX.db"
	python3 -m replayos.cli --config config/replayos.toml --env .env restore-db --input "$(INPUT)"

migrate:
	python3 -m replayos.cli --config config/replayos.toml --env .env migrate-db

vacuum:
	python3 -m replayos.cli --config config/replayos.toml --env .env vacuum-db

service-install:
	python3 -m replayos.cli --config config/replayos.toml --env .env install-service

service-uninstall:
	python3 -m replayos.cli --config config/replayos.toml --env .env uninstall-service

service-status:
	python3 -m replayos.cli --config config/replayos.toml --env .env service-status

zip:
	./scripts/package_zip.sh

docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down
