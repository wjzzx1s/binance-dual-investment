PY := .venv/bin/python
TEX := pdflatex -interaction=nonstopmode -halt-on-error

.PHONY: all fetch analyze data report clean

all: report

fetch:
	$(PY) scripts/fetch.py

analyze:
	$(PY) scripts/analyze.py

data: analyze
	$(PY) scripts/make_report_data.py

report: data
	cd report && $(TEX) main.tex >/tmp/binance-report-1.log && $(TEX) main.tex >/tmp/binance-report-2.log
	@echo "wrote report/main.pdf"

clean:
	rm -f report/main.aux report/main.log report/main.out report/main.pdf
