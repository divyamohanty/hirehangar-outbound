.PHONY: demo test jobs live enrich
demo:      ## full pipeline, offline, $0
	python3 -m hh demo
test:
	python3 -m unittest -v
jobs:      ## pull today's job posts from free ATS APIs
	python3 -m hh jobs --live
enrich:    ## find people + verified emails with treg (needs `treg login`)
	python3 -m hh enrich --live --limit 10
