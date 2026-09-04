.PHONY: test doctor dry-run apply rollback

test:
	@./tests/run

doctor:
	@./bin/doctor

dry-run:
	@./bin/apply --dry-run

apply:
	@./bin/apply

rollback:
	@./bin/rollback $(SNAPSHOT)
