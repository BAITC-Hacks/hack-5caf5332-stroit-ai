# sim francisco (simfrancisco.org), observed 2026-09-23

A "digital twin" of San Francisco: 10,000 synthetic residents sampled from US Census microdata and placed on a pixel-art map. The user asks a yes/no policy question in plain language; the residents "vote" and the map turns green/red. Built at Claude Build Day (June 2026, 2nd place). The live app runs Claude Sonnet 4.6.

Backend: https://sf-digital-twin-tp.fly.dev (CORS open, no auth). Frontend source is saved in src/.

- `GET /cities`: city catalog (slug, bbox, knowledge_date).
- `GET /cities/{c}/news`: recent headlines shown as "INFORMING THE RESIDENTS".
- `POST /simulations {n, seed, start_datetime, tick_seconds, city}`: create a population.
- `GET /branches/{id}/agents?limit&offset`: a resident has id, name, age, educ, race_eth, neighborhood, lonlat, action ("at home") and values {s_cost, s_crime, s_environment, s_homeless, s_housing, s_immigration, trust, change, economic, social}.
- `POST /branches/{id}/chatter {ids}`: short LLM thoughts only for the residents on screen ("groceries cost a fortune").
- `POST /cities/{c}/parse {question}`: classify a free-form question into {supported, framing, question, options}, or {supported:false, reason, examples}.
- `POST /simulations/{id}/branches {ticks, event}`: clone the city, broadcast an event and run a few ticks ("what if" branch).
- `POST /branches/{id}/poll`: returns only aggregate p_yes plus demographic breakdowns plus "what people said". Agents are clustered into at most 160 archetypes before the LLM is called, so latency depends on the number of archetypes, not on N. Results are cached deterministically.
- verdict.js: per-dot green/red is purely visual. A smooth noise field seeded by the question text is thresholded at p_yes, so the on-screen share equals p_yes exactly.

Test poll: "$300M light rail instead of street lighting + police patrols?" returned 37% yes / 63% no in about 15 s, with quotes such as "Public safety concerns outweigh transit".
Credibility claim: backtest on GPT-4o (pre-event cutoff) predicted 81.3% Dem vs actual 83.8% (2024 election) and 70% vs actual 70.38% (2024 Proposition A).
