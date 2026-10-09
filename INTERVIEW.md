# Defend this implementation

Use the application on DEMO-005. Explain the difference between store pending, provider paid and carrier handed_over. State what remains unknown and which records you would compare. Do not assume money is stuck or automatically change the store.

1. Explain why the model can reorder step IDs but cannot generate new causes or actions. Demonstrate invalid output falling back to the verified playbook.
2. Change review thresholds and explain why the snapshot digest changes. The digest records the evidence/policy content, not an immutable database transaction or proof of source truth.
3. Explain why a 120-order synthetic fixture proves coverage of authored cases rather than real merchant accuracy.
4. Identify limitations: optional model ranking has not been tested against a live LLM in this checkpoint; independent provider/carrier fetching is absent; data can become stale after the response.
5. Implement one additional playbook and its evidence rule yourself, then add a test that would fail before the change. Explain the design without reading an AI-written answer.

This AI-assisted project supports discussion of engineering choices. Authorship assistance is documented; personal independent competence needs demonstration, not a title assertion.
