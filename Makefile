.PHONY: test test-native coverage coverage-python coverage-physics lint-docs

test:
	@./tests/run

# These targets also run in .github/ci/Dockerfile, without a live Plasma session.
test-native:
	cmake -S native/rain/tests -B build/ci-physics -DCMAKE_BUILD_TYPE=Release
	cmake --build build/ci-physics --parallel 2
	ctest --test-dir build/ci-physics --output-on-failure
	cmake -S tests/native_rain -B build/ci-native -DCMAKE_BUILD_TYPE=Release
	cmake --build build/ci-native --parallel 2
	@runtime=$$(mktemp -d); \
	trap 'rm -rf "$$runtime"' EXIT; \
	XDG_RUNTIME_DIR="$$runtime" QT_QPA_PLATFORM=xcb QSG_RHI_BACKEND=opengl \
	LIBGL_ALWAYS_SOFTWARE=1 dbus-run-session -- xvfb-run -a \
	ctest --test-dir build/ci-native --output-on-failure --timeout 180

# Core coverage deliberately measures Python helpers and native rain physics.
# See docs/automation.md before interpreting or extending its scope.
coverage: coverage-python coverage-physics

coverage-python:
	mkdir -p build/coverage
	python3 -m coverage erase
	python3 -m coverage run tests/topology_test.py
	python3 -m coverage run tests/polonium_controller_test.py
	python3 -m coverage combine
	python3 -m coverage xml
	python3 -m coverage report

coverage-physics:
	mkdir -p build/coverage
	cmake -E rm -rf build/ci-coverage
	cmake -S native/rain/tests -B build/ci-coverage -DCMAKE_BUILD_TYPE=Release \
		-DCMAKE_CXX_FLAGS=--coverage -DCMAKE_EXE_LINKER_FLAGS=--coverage
	cmake --build build/ci-coverage --parallel 2
	ctest --test-dir build/ci-coverage --output-on-failure
	python3 -m gcovr --root . --filter 'native/rain/dropletsimulation\.(cpp|h)$$' \
		--xml-pretty --print-summary --output build/coverage/physics.xml build/ci-coverage

lint-docs:
	./.github/ci/node_modules/.bin/markdownlint-cli2
