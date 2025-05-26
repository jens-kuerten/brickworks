db-install:
	docker run --name brickworks-postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432  -d postgres:15-alpine
	docker run -d --name redis-stack-brickworks -p 6379:6379 -p 8001:8001 redis/redis-stack:latest

db-run:
	docker container start brickworks-postgres
	docker start redis-stack-brickworks

db-stop:
	docker container stop brickworks-postgres
	docker stop redis-stack-brickworks

patch:
	./tools/release.sh patch

minor:
	./tools/release.sh minor

major:
	./tools/release.sh major
