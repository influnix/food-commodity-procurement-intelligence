# Procurement optimization and inventory accounting

## Policies and public inputs

Seven fixed policies are Fixed; FA/RN/RA SARIMAX; FA/RN/RA LightGBM. Fixed uses80/20t A/B orders subject to arrival admission. FA uses point forecasts in a deterministic LP; RN uses mean scenario cost(λ0); RA uses a CVaR blend(λ.50,α.90). RN/RA share each model's128Planning paths. FA-to-RA mixes forecast-distribution and risk-objective changes; RA-to-RN isolates the objective change on the same scenario input.

Public context contains current stock, promised/overdue pipeline, supplier contracts, demand plan, released history and current-origin forecasts. The evaluator alone owns future price/demand/delay realizations. An overdue receipt is planned for next month without reading its future actual delay.

## Frozen operating assumptions

I200t, empty initial pipeline for policy comparison, planned demand100t/month, warehouse400t. A:premium2%,lead2,monthly cap80t; B:premium8%,lead1,cap100t. Nominal delay0, maximum extra delay1, MOQ/multiple/transport0. Holding3, lost-sales1500, disposal1, terminal deviation9 USD/t, target200t, salvage0. Initial stock acquisition is a sunk cost. A separate Fixed-engine hand fixture has A80/B20 opening pipeline; it is not the comparison default.

## Deterministic planning LP

At origin t plan delivery months m=t+1..e, e=min(t+3,T), and orders k=t..e−1. Nonnegative variables are q(s,k), receipts R, ending stock I, unmet U, disposal W and terminal deviations z+/z−. Only q(s,t) executes; later plans are reoptimized, not carried as confirmed pipeline.

```math
0\le q_{s,k}\le C_s-committed_{s,k},\quad
k+L_s+maximumDelay_s\le e\quad\text{or }q_{s,k}=0,
```

```math
R_m=\sum_s B_{s,m}+\sum_{s,k:k+L_s+nominalDelay_s=m}q_{s,k},
\quad I_m=I_{m-1}+R_m-D_m+U_m-W_m,
```

```math
0\le I_m\le V,\quad0\le U_m\le D_m,\quad W_m=0,
\quad I_e-I^*=z^+-z^-.
```

The objective includes receipt-month forecast price×supplier premium for new orders **and constant existing pipeline**, transport, holding, shortage, disposal and planning terminal deviation. Orders do not lock a market price. Existing pipeline outside the planning window is deferred, not canceled; pipeline after global T is rejected.

W=0 is a deliberate conservative restriction: permitting cheap disposal could violate the engine's greedy-service/overflow-only behavior. Forced pipeline overflow may make this LP infeasible even when the physical engine could dispose of excess. Do not hide this discrepancy with a policy fallback.

## Scenario objective and CVaR

All current/future q, receipts, inventory, unmet/disposal and terminal variables are **shared across price scenarios**. There is no perfect-foresight scenario-specific recourse. Only Cω differs by price, including scenario-specific existing-pipeline constants.

```math
\min (1-\lambda)\sum_\omega p_\omega C_\omega+
\lambda\left(\eta+\frac{1}{1-\alpha}\sum_\omega p_\omega\xi_\omega\right),
\quad \xi_\omega\ge C_\omega-\eta,\quad\xi_\omega\ge0.
```

Discrete CVaR integrates exactly the upper1−αmass, including a fractional boundary atom. For128paths it is not simply the mean of thirteen largest observations. At λ0, η/ξ are not identified by the objective; report their raw epigraph values separately from independently calculated VaR/CVaR. RN matches the deterministic mean-price LP on the same scenarios, not necessarily the original point forecast.

GLOP9.14.6206 uses the existing seed, dual simplex,10second limit, primal/dual1e−8, quantity1e−7t, objective abs1e−4USD/rel1e−8. Accept only OPTIMAL plus VerifySolution, shared-variable, physical/greedy, scenario-cost, expectation/CVaR/objective reconstruction checks. FEASIBLE is not optimal. Tiny execution normalization is limited to declared quantity tolerance; other failures stop the comparison with no hidden fallback.

## Engine and terminal accounting

Monthly sequence: receive → fulfill realized demand → overflow disposal → accrue costs → decision using public state → order. Actual receipt equals order month+lead+evaluator-owned delay. Fulfilled=min(beginning+receipts,demand); shortage is lost sales, charged once without next-month backlog. Ending=beginning+receipts−fulfilled−disposed.

Purchase price is the **receipt month's** index×premium, accrued exactly once. Holding uses ending stock; shortage/disposal use realized quantities. Only the global last month charges9×abs(ending−200). Monthly planning terminal approximations are not accumulated into actual ledger cost.

Validation has36decision origins/38ledger months, Active35/Runoff3. Final locked shape has22/24,Active21/Runoff3. During Runoff no provider/policy call or new q is allowed, including future-plan q after the last origin. End pipeline must be empty. Same-world comparisons keep independent policy states. Failure records preserve origin/cause/confirmed prefix; unavailable partial ledgers are not fabricated or ranked as complete results.
