# 11. Dynamic Lead Qualification Engine and Game-Theoretic Routing

We decided to implement a Dynamic Lead Qualification Engine that evaluates customer signals (urgency score, budget constraints, technical competence requirements) and routes them across five specialized conversational workflows (Hot Lead, On Budget, Solution Eccentric, Trust-Seeking, Cold Lead) governed by a 4-stage funnel state machine (`discovery`, `evaluation`, `negotiation`, `checkout`).

Treating diverse customer archetypes with a generic generative chatbot leads to high churn, hallucinated specs, or abandoned sales. A rational agent routing model ensures hot buyers receive immediate zero-friction checkouts while skeptical or technical leads receive proof points or deep RAG escalation without risking hallucination.
