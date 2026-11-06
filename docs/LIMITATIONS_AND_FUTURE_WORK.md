# Limitations and independent future work

## Data and scientific validity

1. Latest revised World Bank prices may differ from values first published historically. A single snapshot does not reconstruct past vintages.
2. Next-month-end `available_at` is an assumption, not independently observed first-release timing. Revised-snapshot historical simulation is pseudo-real-time.
3. HRW grade changes at2020-07. The boundary is known; a structural break or causal quality-price effect has not been established.
4. Only one commodity/market/history is studied. Gulf benchmark prices do not represent every delivered supplier contract.
5. Historical OOF/rolling forecasts share targets, training history and time dependence. Monthly losses/cost differences are not independent samples.
6. Nominal80% intervals undercovered in Validation. No exchangeability guarantee follows from rolling conformal adjustment here.
7. Joint bootstrap weights are empirical draws, not validated future event probabilities. Separate seeds from one pool are not independent OOS evidence.
8. Price is the modeled uncertainty. Real demand/delay distributions or price–supply correlations were not estimated.

## Operational and economic validity

9. Demand, suppliers, premiums, capacities, stock and costs are synthetic, not observed company operations.
10. The fixed3month planning horizon has no supported H4..6 forecasts. Lag2 requires new correctly timed forecasts/OOF, not relabeling.
11. Shared decisions/physical flows across price scenarios are non-anticipative but not a full adaptive multistage stochastic program.
12. Planned disposal W=0 is conservative. Forced overflow may be feasible in the engine but infeasible in this restricted LP.
13. Initial stock acquisition is sunk; salvage0, terminal deviation, Runoff3months and finite horizon materially affect results. Terminal penalty is not an estimated asset value.
14. The same Validation was used to compare/prefer SARIMAX; model/selection bias remains. Lower LGB simulated cost does not silently change the default specification.
15. Operational sensitivity is post-hoc diagnostic, not independent preregistration. Cells are not independent market trials or frequencies of policy success.
16. Planned scenario CVaR is not long-run realized market CVaR, a service guarantee, corporate savings or an identified causal effect.

## Software qualification and current access

17. Historical synthetic Native/Legacy qualification is separate from actual World Bank source integration. Real Source Export and Seed Runtime remain NOT_VERIFIED.
18. The actual Final Holdout is unevaluated and locked. A future single historical evaluation would still not identify independent repeated market risk.
19. Python source/session guards are API safeguards, not OS security boundaries. Repository exclusion does not itself grant data rights.
20. The clean-checkout contract suite is narrower than the historical613case local archive suite. Missing evidence must not be treated as reproduced.

## Backlog, requiring separate work

- Approved historical-only source Export, external hashes/generation evidence and restricted actual context/Legacy qualification.
- Separately validated real adapter and eligible execution Candidate; only then explicit latest-digest/role/calendar/failure-bound single-evaluation authorization.
- Predeclared coverage/tail/definition/publication/Runoff/terminal sensitivity without overwriting original results or using seen Holdout to choose settings.
- New commodities/markets and genuinely observed business constraints with appropriate data rights and validation.
- Owner-led license/Public decision after [release checks](PUBLIC_RELEASE_CHECKLIST.md).

No new model, tuning, dashboard, NASA source, actual data execution or Public transition is required to close the current portfolio. [Roadmap](../ROADMAP.md) keeps these independent follow-ups separate.
