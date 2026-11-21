import ResourceTrackingRows from "./ResourceTrackingRows";
import { useEffect, useMemo, useState } from "react";
import {
  LayoutDashboard, Users, Activity, Cloud, DollarSign,
  Server, Settings, Search, Bell, Menu, X, Clock,
  ShieldCheck, ArrowUpRight, Layers
} from "lucide-react";
import "./App.css";

const API = import.meta.env.VITE_API_BASE_URL || "";

const navigation = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Employees", icon: Users },
  { name: "Activity Logs", icon: Activity },
  { name: "AWS Services", icon: Cloud },
  { name: "Resource Tracking", icon: Layers },
  { name: "Cost Analysis", icon: DollarSign },
  { name: "AWS Accounts", icon: Server }
];

const colors = [
  "#647cf5", "#13a8a1", "#e8a344", "#9b7aea",
  "#df7caa", "#4b9bd6", "#dc7b57", "#8795a8"
];

const money = value =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2
  }).format(Number(value || 0));

const moneyINR = value =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 2
  }).format(Number(value || 0));


const serviceName = name =>
  name.replace(/^Amazon /, "").replace(/^AWS /, "");

const formatTime = value => {
  if (!value) return "Unknown";
  return new Date(value).toLocaleString();
};

async function getJson(path) {
  const response = await fetch(`${API}${path}`);
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`${response.status}: ${detail}`);
  }
  return response.json();
}

const EMPLOYEE_ACTIVITY_CACHE_KEY = "cloudpilot-verified-employee-activity-v1";
const EMPLOYEE_ACTIVITY_CACHE_DAYS = 90;

function readEmployeeActivityCache() {
  try {
    const value = JSON.parse(window.localStorage.getItem(EMPLOYEE_ACTIVITY_CACHE_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch { return []; }
}

function mergeEmployeeActivity(existing, incoming) {
  const cutoff = Date.now() - EMPLOYEE_ACTIVITY_CACHE_DAYS * 86400000;
  const byEventId = new Map();
  for (const event of [...existing, ...incoming]) {
    if (event?.actor_type !== "human_sso" || event?.identity_verified !== true || !event?.identity_id || !event?.event_id || !event?.event_time) continue;
    const timestamp = new Date(event.event_time).getTime();
    if (!Number.isFinite(timestamp) || timestamp < cutoff) continue;
    byEventId.set(event.event_id, event);
  }
  return [...byEventId.values()].sort((a, b) => new Date(b.event_time) - new Date(a.event_time));
}

function App() {
  const [page, setPage] = useState("Overview");
  const [account, setAccount] = useState("all");
  const [employeeFilter, setEmployeeFilter] = useState("all");
  const [visibleEmployeeCount, setVisibleEmployeeCount] = useState(5);
  const EMPLOYEES_PER_PAGE = 5;
  const [serviceFilter, setServiceFilter] = useState("all");
  const [activityTypeFilter, setActivityTypeFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [activityHours, setActivityHours] = useState("24");
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const [accounts, setAccounts] = useState([]);
  const [costResults, setCostResults] = useState([]);
  const [activityResults, setActivityResults] = useState([]);
  const [rememberedHumanEvents, setRememberedHumanEvents] = useState(() => readEmployeeActivityCache());
  const [selectedEmployeeId, setSelectedEmployeeId] = useState(null);
  const [inventoryResults, setInventoryResults] = useState([]);

  const [loading, setLoading] = useState(true);
  const [errors, setErrors] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshMinutes, setRefreshMinutes] = useState("10");
  const [refreshTick, setRefreshTick] = useState(0);
  const [usdInrRate, setUsdInrRate] = useState(null);
  const [fxRateDate, setFxRateDate] = useState(null);
  const [fxRateError, setFxRateError] = useState(false);



  useEffect(() => {
    let cancelled = false;

    async function loadAccounts() {
      try {
        const data = await getJson("/api/accounts");
        if (!cancelled) setAccounts(data.accounts || []);
      } catch (error) {
        if (!cancelled) setErrors([`Accounts: ${error.message}`]);
      }
    }

    loadAccounts();
    return () => { cancelled = true; };
  }, []);

  useEffect(() => {
    if (!accounts.length) return;

    let cancelled = false;

    async function loadDashboard() {
      setLoading(true);
      setErrors([]);

      const selected = account === "all"
        ? accounts
        : accounts.filter(item => item.account_id === account);

      const costCalls = selected.map(async item => {
        try {
          const data = await getJson(
            `/api/costs/services/${item.account_id}`
          );
          return { ...data, account_name: item.account_name };
        } catch (error) {
          return {
            account_id: item.account_id,
            account_name: item.account_name,
            error: error.message
          };
        }
      });

      const inventoryCalls = selected.map(async item => {
        try {
          const data = await getJson(
            `/api/inventory/${item.account_id}`
          );
          return data;
        } catch (error) {
          return {
            account_id: item.account_id,
            account_name: item.account_name,
            error: error.message
          };
        }
      });

      const activityCalls = selected.map(async item => {
        try {
          const data = await getJson(
            `/api/activity/recent/${item.account_id}?hours=${activityHours}`
          );
          return data.events || [];
        } catch (error) {
          return { error: `${item.account_name}: ${error.message}` };
        }
      });

      const [costs, activities, inventories] = await Promise.all([
        Promise.all(costCalls),
        Promise.all(activityCalls),
        Promise.all(inventoryCalls)
      ]);

      if (cancelled) return;

      setCostResults(costs);
      setInventoryResults(inventories);

      const events = activities.flatMap(result =>
        Array.isArray(result) ? result : []
      );

      events.sort(
        (a, b) => new Date(b.event_time) - new Date(a.event_time)
      );

      setActivityResults(events);

      const failures = [
        ...costs.filter(item => item.error)
          .map(item => `${item.account_name} costs: ${item.error}`),
        ...activities.filter(item => !Array.isArray(item))
          .map(item => item.error)
      ];

      setErrors(failures);
      setLastUpdated(new Date());
      setLoading(false);
    }

    loadDashboard();

    return () => { cancelled = true; };
  }, [accounts, account, activityHours, refreshTick]);


  // Reliable Grafana-style dashboard auto-refresh.
  useEffect(() => {
    const intervalMs = Number(refreshMinutes) * 60 * 1000;
    let lastTriggered = Date.now();

    const triggerRefresh = () => {
      if (document.visibilityState !== "visible") return;

      // Avoid duplicate refreshes when focus and visibility fire together.
      const now = Date.now();
      if (now - lastTriggered < 3000) return;

      lastTriggered = now;
      setRefreshTick(value => value + 1);
    };

    const timerId = window.setInterval(
      triggerRefresh,
      intervalMs
    );

    const handleVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        triggerRefresh();
      }
    };

    window.addEventListener("focus", triggerRefresh);
    document.addEventListener(
      "visibilitychange",
      handleVisibilityChange
    );

    return () => {
      window.clearInterval(timerId);
      window.removeEventListener("focus", triggerRefresh);
      document.removeEventListener(
        "visibilitychange",
        handleVisibilityChange
      );
    };
  }, [refreshMinutes]);


  // Fetch a daily USD/INR reference rate and cache it for 24 hours.
  useEffect(() => {
    let cancelled = false;
    const cacheKey = "cloudpilot-usd-inr-rate";
    const cacheMaxAge = 24 * 60 * 60 * 1000;

    async function loadExchangeRate() {
      try {
        const cached = JSON.parse(localStorage.getItem(cacheKey) || "null");

        if (
          cached &&
          Number.isFinite(Number(cached.rate)) &&
          Date.now() - cached.fetchedAt < cacheMaxAge
        ) {
          if (!cancelled) {
            setUsdInrRate(Number(cached.rate));
            setFxRateDate(cached.date || null);
          }
          return;
        }
      } catch {
        // Ignore invalid browser cache and fetch a fresh rate.
      }

      try {
        const response = await fetch(
          "https://api.frankfurter.dev/v2/rate/USD/INR"
        );

        if (!response.ok) {
          throw new Error(`Exchange-rate request failed: ${response.status}`);
        }

        const data = await response.json();
        const rate = Number(data.rate);

        if (!Number.isFinite(rate) || rate <= 0) {
          throw new Error("Invalid USD/INR exchange rate");
        }

        const cache = {
          rate,
          date: data.date,
          fetchedAt: Date.now()
        };

        localStorage.setItem(cacheKey, JSON.stringify(cache));

        if (!cancelled) {
          setUsdInrRate(rate);
          setFxRateDate(data.date || null);
          setFxRateError(false);
        }
      } catch (error) {
        if (!cancelled) {
          setFxRateError(true);
          console.error("USD/INR rate unavailable:", error);
        }
      }
    }

    loadExchangeRate();

    return () => {
      cancelled = true;
    };
  }, []);

  const successfulCosts = costResults.filter(item => !item.error);

  const totalCost = successfulCosts.reduce(
    (sum, item) => sum + Number(item.total || 0), 0
  );

  const dailyCost = successfulCosts.reduce(
    (sum, item) => sum + Number(item.daily_total || 0), 0
  );

  const monthlyCost = totalCost;
  const billingPeriod = successfulCosts.find(item => item.period)?.period;

  const formatBillingRange = period => {
    if (!period?.start || !period?.today) return "Billing period unavailable";

    const formatDate = value => new Date(`${value}T00:00:00`).toLocaleDateString(
      "en-IN",
      { day: "2-digit", month: "short", year: "numeric" }
    );

    return `${formatDate(period.start)} – ${formatDate(period.today)}`;
  };

  const billingRange = formatBillingRange(billingPeriod);


  const currentDate = new Date().toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });

  const services = useMemo(() => {
    const grouped = new Map();

    successfulCosts.forEach(accountCost => {
      (accountCost.services || []).forEach(service => {
        const current = grouped.get(service.service) || 0;
        grouped.set(service.service, current + Number(service.amount || 0));
      });
    });

    return [...grouped.entries()]
      .map(([name, amount], index) => ({
        name,
        amount,
        color: colors[index % colors.length]
      }))
      .sort((a, b) => b.amount - a.amount);
  }, [costResults]);

  const currentHumanEvents = activityResults.filter(event =>
    event.actor_type === "human_sso" && event.identity_verified === true && event.identity_id
  );

  // Browser-local interim history. Server-side persistence will replace this later.
  useEffect(() => {
    const merged = mergeEmployeeActivity(rememberedHumanEvents, currentHumanEvents);
    setRememberedHumanEvents(previous => {
      if (JSON.stringify(previous) === JSON.stringify(merged)) return previous;
      try { window.localStorage.setItem(EMPLOYEE_ACTIVITY_CACHE_KEY, JSON.stringify(merged)); }
      catch (error) { console.warn("Could not persist employee activity in browser storage:", error); }
      return merged;
    });
  }, [activityResults]);

  const humanEvents = useMemo(
    () => mergeEmployeeActivity(rememberedHumanEvents, currentHumanEvents),
    [rememberedHumanEvents, activityResults]
  );

  const istDateKey = value => new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit", day: "2-digit"
  }).format(new Date(value));

  const todayKey = istDateKey(new Date());
  const yesterdayDate = new Date();
  yesterdayDate.setDate(yesterdayDate.getDate() - 1);
  const yesterdayKey = istDateKey(yesterdayDate);

  const employeeActivity = (() => {
    const grouped = new Map();
    for (const event of humanEvents) {
      const key = event.identity_id;
      if (!key) continue;
      if (!grouped.has(key)) grouped.set(key, {
        identity_id: key, actor: event.actor || "Unknown employee", events: [], services: new Set()
      });
      const employee = grouped.get(key);
      employee.events.push(event);
      if (event.event_source) employee.services.add(event.event_source.replace(/\.amazonaws\.com$/, ""));
    }
    return [...grouped.values()].map(employee => {
      employee.events.sort((a, b) => new Date(b.event_time) - new Date(a.event_time));
      const latest = employee.events[0];
      const ageMinutes = Math.max(0, (Date.now() - new Date(latest.event_time).getTime()) / 60000);
      const dateKey = istDateKey(latest.event_time);
      const activityDay = dateKey === todayKey ? "Today" : dateKey === yesterdayKey ? "Yesterday" : "Older";
      return {
        ...employee, latest, services: [...employee.services], ageMinutes, activityDay,
        todayEventCount: employee.events.filter(event => istDateKey(event.event_time) === todayKey).length,
        status: ageMinutes <= 10 ? "Active recently" : ageMinutes <= 30 ? "Recently active" : activityDay === "Today" ? "Earlier today" : activityDay === "Yesterday" ? "Last active yesterday" : "Inactive"
      };
    }).sort((a, b) => {
      const order = { Today: 0, Yesterday: 1, Older: 2 };
      return order[a.activityDay] - order[b.activityDay] || new Date(b.latest.event_time) - new Date(a.latest.event_time);
    });
  })();

  const todayEmployeeActivity = employeeActivity.filter(employee => employee.activityDay === "Today");
  const todayHumanEvents = humanEvents.filter(event => istDateKey(event.event_time) === todayKey);
  const selectedEmployee = employeeActivity.find(employee => employee.identity_id === selectedEmployeeId);

  const formatIST = value =>
    new Date(value).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true
    });

  const uniqueHumanCount = new Set(
    humanEvents
      .map(event => event.identity_id)
      .filter(Boolean)
  ).size;

  const filteredActivities = activityResults.filter(event => {
    const text = [
      event.actor, event.event_name, event.event_source,
      event.actor_type, event.account_id
    ].join(" ").toLowerCase();

    const matchesSearch = text.includes(search.toLowerCase());

    const matchesEmployee =
      employeeFilter === "all" ||
      event.identity_id === employeeFilter;

    const matchesService =
      serviceFilter === "all" ||
      event.event_source === serviceFilter;

    const matchesActivity =
      activityTypeFilter === "all" ||
      (activityTypeFilter === "read" && event.read_only === true) ||
      (activityTypeFilter === "write" && event.read_only === false) ||
      (activityTypeFilter === "unknown" && event.read_only == null);

    return matchesSearch && matchesEmployee &&
      matchesService && matchesActivity;
  });

  const accountNames = Object.fromEntries(
    accounts.map(item => [item.account_id, item.account_name])
  );

  const activePeriod = successfulCosts[0]?.period;

  const visibleAccounts = account === "all"
    ? accounts
    : accounts.filter(item => item.account_id === account);


  return (
    <div className="app-shell">
      <aside className={`sidebar ${sidebarOpen ? "sidebar-open" : ""}`}>
        <div className="brand">
          <div className="brand-icon"><Cloud size={23} /></div>
          <div><h2>CloudPilot</h2><span>FINOPS PLATFORM</span></div>
          <button className="mobile-close" onClick={() => setSidebarOpen(false)}>
            <X />
          </button>
        </div>

        <p className="nav-label">WORKSPACE</p>
        <nav>
          {navigation.map(item => {
            const Icon = item.icon;
            return (
              <button key={item.name}
                className={`nav-item ${page === item.name ? "selected" : ""}`}
                onClick={() => {
                  setPage(item.name);
                  setSidebarOpen(false);
                }}>
                <Icon size={18} /> {item.name}
              </button>
            );
          })}
        </nav>

        <div className="sidebar-bottom">
          <div className="security-card">
            <ShieldCheck size={21} />
            <strong>Monitoring Center</strong>
            <span>AWS cost and audit monitoring</span>
            <span className="secure-status">
              ● {errors.length ? "Partial connectivity" : "API connected"}
            </span>
          </div>
          <button className="nav-item"><Settings size={18} /> Settings</button>
          <div className="profile">
            <div className="avatar">AD</div>
            <div><strong>Admin User</strong><span>Administrator</span></div>
          </div>
        </div>
      </aside>

      {sidebarOpen && (
        <div className="overlay" onClick={() => setSidebarOpen(false)} />
      )}

      <main className="main-area">
        <header className="topbar">
          <div className="topbar-left">
            <button className="mobile-menu" onClick={() => setSidebarOpen(true)}>
              <Menu />
            </button>
            <div>
              <div className="breadcrumb">Workspace / <strong>{page}</strong></div>
              <h1>{page}</h1>
            </div>
          </div>

          <div className="top-actions">
              <select
                aria-label="Dashboard refresh interval"
                title="Automatic dashboard refresh"
                value={refreshMinutes}
                onChange={e => setRefreshMinutes(e.target.value)}
              >
                <option value="1">Refresh: 1 minute</option>
                <option value="5">Refresh: 5 minutes</option>
                <option value="10">Refresh: 10 minutes</option>
                <option value="30">Refresh: 30 minutes</option>
                <option value="60">Refresh: 1 hour</option>
              </select>
              <button
                type="button"
                className="icon-button"
                title="Refresh dashboard now"
                aria-label="Refresh dashboard now"
                disabled={loading}
                onClick={() => setRefreshTick(value => value + 1)}
              >
                ↻
              </button>
              <span className="refresh-last-updated">
                {lastUpdated
                  ? `Updated ${lastUpdated.toLocaleTimeString("en-IN")}`
                  : "Not refreshed yet"}
              </span>

            <select value={account} onChange={e => setAccount(e.target.value)}>
              <option value="all">All Connected Accounts</option>
              {accounts.map(item => (
                <option key={item.account_id} value={item.account_id}>
                  {item.account_name}
                </option>
              ))}
            </select>
            <button className="icon-button"><Bell size={18} /></button>
            <div className="top-avatar">AD</div>
          </div>
        </header>

        <div className="content">
          <div className="welcome-row">
            <div>
              <h2>AWS Infrastructure Overview</h2>
              <p>Live AWS cost and CloudTrail monitoring.</p>
            </div>
            <span className="demo-label">
              ● {loading ? "LOADING" : "LIVE API DATA"}
            </span>
          </div>

          {errors.map((error, index) => (
            <div className="panel" key={index}>
              <p className="footnote">{error}</p>
            </div>
          ))}

          {page === "Overview" && <>
            <section className="panel account-overview">
              <PanelTitle
                title="AWS Account Cost Overview"
                subtitle={`Current date: ${currentDate}`}
              />
              <div className="account-cost-grid">
                {visibleAccounts.map(item => {
                  const cost = costResults.find(
                    result => result.account_id === item.account_id
                  );

                  return (
                    <div className="account-cost-card" key={item.account_id}>
                      <div className="account-cost-heading">
                        <strong>{item.account_name}</strong>
                        <span>{item.authenticated ? "Connected" : "Not authenticated"}</span>
                      </div>
                      <p>Account ID: {item.account_id}</p>
                      {cost?.error ? (
                        <p className="error-text">Cost unavailable: {cost.error}</p>
                      ) : cost ? (
                        <div className="account-cost-values">
                          <div>
                            <span>Today's cost</span>
                            <strong>{money(cost.daily_total)}</strong>
                          </div>
                          <div>
                            <span>Monthly cost ({formatBillingRange(cost.period)})</span>
                            <strong>{money(cost.total)}</strong>
                          </div>
                        </div>
                      ) : (
                        <p>Loading cost information...</p>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
            <section className="stats-grid">
              <div className="panel stat-card total-cost-stat">
                <div className="stat-top">
                  <span>Total AWS Cost</span>
                  <div className="stat-icon"><DollarSign size={19} /></div>
                </div>

                <div className="stat-value">
                  {loading ? "Loading..." : money(totalCost)}
                </div>

                <div className="total-cost-breakdown">
                  {successfulCosts.map(item => (
                    <div className="total-cost-account" key={item.account_id}>
                      <span className="total-cost-account-name"
                        title={item.account_id}>
                        {item.account_name}
                      </span>
                      <span className="total-cost-account-values">
                        <strong>{money(item.total)}</strong>
                        {usdInrRate !== null && (
                          <small>{moneyINR(Number(item.total || 0) * usdInrRate)}</small>
                        )}
                      </span>
                    </div>
                  ))}
                </div>

                <div className="total-cost-converted">
                  <span>Total in INR</span>
                  <strong>
                    {usdInrRate !== null
                      ? moneyINR(totalCost * usdInrRate)
                      : "Exchange rate unavailable"}
                  </strong>
                </div>

                <div className="stat-note">
                  {`Billing period: ${billingRange}`}
                </div>

                <div className="total-cost-rate">
                  {usdInrRate !== null
                    ? `1 USD = ${usdInrRate.toFixed(4)} INR · Rate date: ${fxRateDate || "Not provided"}`
                    : fxRateError
                      ? "USD/INR reference rate unavailable"
                      : "Loading USD/INR reference rate..."}
                </div>
              </div>
              <Stat title="Employees Active Today"
                value={String(todayEmployeeActivity.length).padStart(2, "0")}
                note="Unique verified employees with AWS activity today (IST)"
                icon={Users} />
              
              
            </section>

            <section className="inventory-section">
              <div className="inventory-section-heading">
                <h3>AWS Infrastructure Inventory</h3>
                <p>Live resource counts by monitored AWS account · us-east-1</p>
              </div>

              <div className="inventory-account-grid">
                {inventoryResults.map(item => {
                  const eks = item.eks || {};
                  const vpcs = item.vpcs || {};
                  const rds = item.rds || {};
                  const volumes = item.volumes || {};
                  const kubernetes = item.kubernetes || {};

                  const countValue = section =>
                    section.status === "ok" && section.count !== null &&
                    section.count !== undefined
                      ? section.count
                      : "Unavailable";

                  const kubeValue = key =>
                    kubernetes.status === "not_configured"
                      ? "Not configured"
                      : kubernetes[key] ?? "Unavailable";

                  return (
                    <div className="inventory-account-card" key={item.account_id}>
                      <div className="inventory-account-heading">
                        <div>
                          <strong>{item.account_name}</strong>
                          <span>Account ID: {item.account_id}</span>
                        </div>
                        <span className="inventory-region">
                          {item.region || "AWS"}
                        </span>
                      </div>

                      {item.error ? (
                        <p className="inventory-error">
                          Inventory unavailable: {item.error}
                        </p>
                      ) : (
                        <>
                          <div className="inventory-cluster-block">
                            <div>
                              <span>EKS Clusters</span>
                              <strong>{countValue(eks)}</strong>
                            </div>
                            <div className="inventory-cluster-names">
                              {eks.clusters?.length
                                ? eks.clusters.map(name => (
                                    <span key={name}>{name}</span>
                                  ))
                                : <span>No cluster names available</span>}
                            </div>
                          </div>

                          <div className="inventory-count-grid">
                            <InventoryMetric
                              label="Kubernetes Nodes"
                              value={kubeValue("nodes")}
                            />
                            <InventoryMetric
                              label="Kubernetes Pods"
                              value={kubeValue("pods")}
                            />
                            <InventoryMetric
                              label="VPCs"
                              value={countValue(vpcs)}
                            />
                            <InventoryMetric
                              label="RDS Databases"
                              value={countValue(rds)}
                            />
                            <InventoryMetric
                              label="EBS Volumes"
                              value={countValue(volumes)}
                            />
                          </div>

                          {item.errors?.length > 0 && (
                            <p className="inventory-note">
                              Some inventory sections could not be retrieved.
                            </p>
                          )}
                        </>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="middle-grid">
              <div className="panel">
                <PanelTitle title="AWS Spending"
                  subtitle="Real Cost Explorer service breakdown" />
                <div className="total-cost">
                  {money(totalCost)} <span>USD / current month</span>
                </div>
                {services.slice(0, 10).map((item, index) => (
                  <CostBar key={item.name} item={item}
                    max={services[0]?.amount || 1} />
                ))}
                {!services.length && <p className="empty">No cost data available.</p>}
                <p className="footnote">
                  {activePeriod
                    ? `Period: ${activePeriod.start} to ${activePeriod.end_exclusive} (end exclusive).`
                    : "Cost period unavailable."}
                </p>
              </div>

              <div className="panel today-employee-panel">
                <PanelTitle
                  title="AWS Employee Activity"
                  subtitle="Verified Identity Center activity · today and previous activity · IST"
                />

                <div className="today-activity-metrics">
                  <div>
                    <span>Employees active today</span>
                    <strong>{todayEmployeeActivity.length}</strong>
                  </div>
                  <div>
                    <span>AWS API activities today</span>
                    <strong>{todayHumanEvents.length}</strong>
                  </div>
                </div>

                <div className="activity-status-legend">
                  <span><i className="status-dot status-green" /> Active within 10 min</span>
                  <span><i className="status-dot status-yellow" /> Active within 10–30 min</span>
                  <span><i className="status-dot status-grey" /> Earlier / inactive</span>
                </div>
                <div className="today-employee-list">
                  {employeeActivity.slice(0, visibleEmployeeCount).map(employee => {
                    const latest = employee.latest;
                    const dotClass = employee.ageMinutes <= 10 ? "status-green" : employee.ageMinutes <= 30 ? "status-yellow" : "status-grey";
                    return (
                      <button type="button" className="today-employee-row employee-row-button" key={employee.identity_id}
                        onClick={() => { setSelectedEmployeeId(employee.identity_id); setPage("Employees"); }}>
                        <div className="today-employee-avatar">{(employee.actor || "?").slice(0, 2).toUpperCase()}</div>
                        <div className="today-employee-main">
                          <strong>{employee.actor}</strong>
                          <span>{accountNames[latest.account_id] || latest.account_id} · {employee.todayEventCount} events today · {employee.events.length} stored events</span>
                          <span>{employee.activityDay} · Services: {employee.services.length ? employee.services.join(", ") : "Unknown"}</span>
                        </div>
                        <div className="today-employee-last">
                          <span className="today-employee-status"><i className={`status-dot ${dotClass}`} />{employee.status}</span>
                          <strong>{latest.event_name || "Unknown action"}</strong>
                          <span>{formatIST(latest.event_time)}</span>
                        </div>
                      </button>
                    );
                  })}
                  {!employeeActivity.length && <p className="empty">No verified employee activity has been observed yet.</p>}
                </div>

                {employeeActivity.length > visibleEmployeeCount && (
                  <div className="employee-view-more">
                    <button
                      type="button"
                      onClick={() =>
                        setVisibleEmployeeCount(count =>
                          Math.min(count + EMPLOYEES_PER_PAGE, employeeActivity.length)
                        )
                      }
                    >
                      View more employees
                      <span>
                        ({employeeActivity.length - visibleEmployeeCount} remaining)
                      </span>
                    </button>
                  </div>
                )}

                {visibleEmployeeCount > EMPLOYEES_PER_PAGE && (
                  <div className="employee-view-more">
                    <button
                      type="button"
                      onClick={() => setVisibleEmployeeCount(EMPLOYEES_PER_PAGE)}
                    >
                      Show less
                    </button>
                  </div>
                )}

                <p className="footnote">
                  Based on verified Identity Center CloudTrail API events.
                  This is recent activity, not proof of an active console session
                  or employee attendance.
                </p>
              </div>
            </section>

            <section className="panel">
              <PanelTitle title="Recent AWS Activity"
                subtitle="CloudTrail events returned by AWS" />
              <ActivityTable rows={activityResults.slice(0, 10)}
                accountNames={accountNames} />
              <button className="text-button"
                onClick={() => setPage("Activity Logs")}>
                View all activity →
              </button>
            </section>
          </>}

          {page === "Employees" && <section className="panel">
            <PanelTitle title="Employee Activity Directory" subtitle="Verified Identity Center users observed in CloudTrail" />
            <p className="employee-cache-notice">This frontend temporarily remembers observed employees in this browser for up to 90 days. It is not yet a central employee directory.</p>
            <div className="employee-directory-layout">
              <div className="employee-directory-list">
                {employeeActivity.map(employee => (
                  <button type="button" key={employee.identity_id}
                    className={`employee-directory-item ${selectedEmployeeId === employee.identity_id ? "selected" : ""}`}
                    onClick={() => setSelectedEmployeeId(employee.identity_id)}>
                    <span className="today-employee-avatar">{(employee.actor || "?").slice(0, 2).toUpperCase()}</span>
                    <span className="employee-directory-name"><strong>{employee.actor}</strong><small>{employee.activityDay} · {formatIST(employee.latest.event_time)}</small></span>
                    <span className="employee-directory-count">{employee.events.length}</span>
                  </button>
                ))}
                {!employeeActivity.length && <p className="empty">No cached verified employees yet. Refresh the dashboard after AWS activity is available.</p>}
              </div>
              <div className="employee-detail">
                {selectedEmployee ? <>
                  <div className="employee-detail-header">
                    <div className="today-employee-avatar">{(selectedEmployee.actor || "?").slice(0, 2).toUpperCase()}</div>
                    <div><h3>{selectedEmployee.actor}</h3><p>{selectedEmployee.identity_id}</p><small>Latest activity: {formatIST(selectedEmployee.latest.event_time)}</small></div>
                  </div>
                  <div className="employee-detail-stats">
                    <div><strong>{selectedEmployee.events.length}</strong><span>Stored events</span></div>
                    <div><strong>{selectedEmployee.todayEventCount}</strong><span>Today (IST)</span></div>
                    <div><strong>{selectedEmployee.services.length}</strong><span>AWS services</span></div>
                  </div>
                  <h4>Activity history</h4>
                  <div className="employee-history">
                    {selectedEmployee.events.map(event => <div className="employee-history-row" key={event.event_id}>
                      <div><strong>{event.event_name}</strong><span>{event.event_source} · {accountNames[event.account_id] || event.account_id}</span></div>
                      <time>{formatIST(event.event_time)}</time>
                    </div>)}
                  </div>
                </> : <p className="empty">Select an employee to view their activity history.</p>}
              </div>
            </div>
          </section>}

          {page === "Resource Tracking" && (
            <section className="resource-tracking">

              <div className="resource-header">
                <div>
                  <h2>AWS Resource Tracking</h2>
                  <p>
                    Track AWS resource creation, employee identity,
                    history and costs across connected accounts.
                  </p>
                </div>
              </div>

              <div className="resource-stats">

                <div className="panel resource-stat">
                  <span>Total Resources</span>
                  <strong>—</strong>
                  <small>All monitored accounts</small>
                </div>

                <div className="panel resource-stat">
                  <span>Created Today</span>
                  <strong>—</strong>
                  <small>New resources today</small>
                </div>

                <div className="panel resource-stat">
                  <span>Active Resources</span>
                  <strong>—</strong>
                  <small>Currently active</small>
                </div>

                <div className="panel resource-stat">
                  <span>Deleted Resources</span>
                  <strong>—</strong>
                  <small>Historical records retained</small>
                </div>

              </div>

              <div className="panel resource-table-panel">

                <div className="resource-table-header">
                  <div>
                    <h3>Resource Creation History</h3>
                    <p>Employee-wise AWS resource records</p>
                  </div>
                </div>

                <div className="resource-table-scroll">
                  <table className="resource-table">
                    <thead>
                      <tr>
                        <th>Resource ID</th>
                        <th>Resource Type</th>
                        <th>Employee</th>
                        <th>AWS Account</th>
                        <th>Region</th>
                        <th>Created At</th>
                        <th>Estimated Cost</th>
                        <th>Status</th>
                      </tr>
                    </thead>

                    <ResourceTrackingRows />
                  </table>
                </div>

              </div>

            </section>
          )}

          {page === "Activity Logs" && <section className="panel">
            <PanelTitle title="AWS Audit Explorer"
              subtitle="Recent CloudTrail events from connected accounts" />
            <div className="filters">
              <div className="search-box">
                <Search size={17} />
                <input placeholder="Search actor, event or service..."
                  value={search}
                  onChange={e => setSearch(e.target.value)} />
              </div>
            </div>
            <ActivityTable rows={filteredActivities}
              accountNames={accountNames} />
            {!filteredActivities.length &&
              <p className="empty">No matching events found.</p>}
          </section>}

          {page === "AWS Services" && <section className="service-grid">
            {services.map((item, index) => (
              <div className="panel service-card" key={item.name}>
                <Cloud size={26} style={{ color: colors[index % colors.length] }} />
                <h3>{serviceName(item.name)}</h3>
                <p>Current-month cost</p>
                <strong>{money(item.amount)}</strong>
                <span>Cost Explorer data</span>
              </div>
            ))}
            {!services.length && <p className="empty">No service costs available.</p>}
          </section>}

          {page === "Cost Analysis" && <section className="panel">
            <PanelTitle title="AWS Cost Analysis"
              subtitle="Current-month Cost Explorer results" />
            <div className="total-cost">{money(totalCost)}
              <span>USD / current month</span>
            </div>
            {services.map(item => (
              <CostBar key={item.name} item={item}
                max={services[0]?.amount || 1} />
            ))}
            <p className="footnote">
              Account-level cost aggregation. Employee or resource attribution
              is not available from this API.
            </p>
          </section>}

          {page === "AWS Accounts" && <section className="panel">
            <PanelTitle title="Connected AWS Accounts"
              subtitle="Accounts returned by the backend STS checks" />
            {accounts.map(item => (
              <div className="account-row" key={item.account_id}>
                <Cloud size={23} />
                <div>
                  <strong>{item.account_name}</strong>
                  <span>Account ID: {item.account_id}</span>
                </div>
                <span className="account-status">
                  ● {item.status}
                </span>
              </div>
            ))}
          </section>}

          <footer>
            CloudPilot FinOps Platform · AWS API data
            {lastUpdated && ` · Updated ${lastUpdated.toLocaleTimeString()}`}
          </footer>
        </div>
      </main>
    </div>
  );
}

function InventoryMetric({ label, value }) {
  return (
    <div className="inventory-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function Stat({ title, value, note, icon: Icon }) {
  return (
    <div className="panel stat-card">
      <div className="stat-top">
        <span>{title}</span>
        <div className="stat-icon"><Icon size={19} /></div>
      </div>
      <div className="stat-value">{value}</div>
      <div className="stat-note">{note} <ArrowUpRight size={13} /></div>
    </div>
  );
}

function PanelTitle({ title, subtitle }) {
  return (
    <div className="panel-heading">
      <div><h3>{title}</h3><p>{subtitle}</p></div>
    </div>
  );
}

function CostBar({ item, max }) {
  return (
    <div className="bar-row">
      <span>{serviceName(item.name)}</span>
      <div className="bar-track">
        <div style={{
          width: `${Math.min(100, item.amount / max * 100)}%`,
          background: item.color
        }} />
      </div>
      <strong>{money(item.amount)}</strong>
    </div>
  );
}

function ActivityTable({ rows, accountNames }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Actor</th><th>Event</th><th>Service</th>
            <th>Actor Type</th><th>Account</th><th>Time</th>
            <th>Operation</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((event, index) => (
            <tr key={event.event_id || index}>
              <td><strong>{event.actor || "Unknown"}</strong></td>
              <td><code>{event.event_name}</code></td>
              <td>{event.event_source}</td>
              <td>{event.actor_type}</td>
              <td>{accountNames[event.account_id] || event.account_id}</td>
              <td>{formatTime(event.event_time)}</td>
              <td>{event.read_only ? "Read-only" : "API write operation"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default App;
