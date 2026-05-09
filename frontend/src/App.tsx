import { FormEvent, useEffect, useState } from "react";
import { Bar, Doughnut, Line } from "react-chartjs-2";
import {
  ArcElement,
  BarElement,
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
} from "chart.js";

import { apiDownload, apiFetch, clearAuthToken, setAuthToken } from "./lib/api";
import type {
  BlockStat,
  CategoryBreakdownPoint,
  CollectionRecord,
  LoginResponse,
  OperatorStat,
  PaginatedCollections,
  PaginatedWasteEntries,
  ProcessingTotals,
  SummaryMetric,
  TrendPoint,
  User,
  WasteEntry,
  WetProcessingStatus,
} from "./types";

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  ArcElement,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
);

const SOURCE_LOCATIONS = [
  "Housing Block",
  "Sports Complex",
  "Hostel Area",
  "Food Outlet",
  "Academic Area",
  "Research Park",
  "Other Public Bin",
];
const DRY_SUBTYPES = ["Paper", "Plastic", "Glass", "Metal", "Cardboard", "Mixed Dry"];
const WET_SUBTYPES = ["Food Waste", "Kitchen Waste", "Garden Waste", "Mixed Organics"];

interface DashboardBundle {
  summary: { metrics: SummaryMetric[] };
  trends: TrendPoint[];
  categoryBreakdown: CategoryBreakdownPoint[];
  blocks: BlockStat[];
  operators: OperatorStat[];
}

function getToday() {
  return new Date().toISOString().slice(0, 10);
}

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleDateString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

function formatDateInput(value: string) {
  return formatDate(value);
}

function formatDateTime(value: string) {
  const hasTimezone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(value);
  const date = new Date(hasTimezone ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatWeight(value: number | string) {
  return `${Number(value).toFixed(2)} kg`;
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-4 py-5 text-sm text-slate-500">
      {message}
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  body,
}: {
  eyebrow: string;
  title: string;
  body?: string;
}) {
  return (
    <div className="mb-4">
      <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">{eyebrow}</p>
      <h2 className="mt-2 text-lg font-semibold text-slate-900">{title}</h2>
      {body ? <p className="mt-1 max-w-3xl text-sm leading-6 text-slate-600">{body}</p> : null}
    </div>
  );
}

function MetricCard({ label, value }: SummaryMetric) {
  return (
    <article className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <p className="text-sm font-medium text-slate-500">{label}</p>
      <p className="mt-2 text-xl font-semibold text-slate-900">{value}</p>
    </article>
  );
}

function DataTable({
  headers,
  rows,
  emptyMessage,
  maxHeightClass,
}: {
  headers: string[];
  rows: Array<Array<string | number>>;
  emptyMessage: string;
  maxHeightClass?: string;
}) {
  if (!rows.length) {
    return <EmptyState message={emptyMessage} />;
  }

  return (
    <div
      className={`overflow-x-auto overflow-y-auto rounded-xl border border-slate-200 ${maxHeightClass ?? ""}`}
    >
      <table className="min-w-full divide-y divide-slate-200 text-sm">
        <thead className="bg-slate-50">
          <tr>
            {headers.map((header) => (
              <th
                key={header}
                className="px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-[0.16em] text-slate-500"
              >
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-200 bg-white">
          {rows.map((row, rowIndex) => (
            <tr key={`${rowIndex}-${row[0]}`}>
              {row.map((cell, cellIndex) => (
                <td key={`${rowIndex}-${cellIndex}`} className="px-3 py-2.5 text-slate-700">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [sessionReady, setSessionReady] = useState(false);
  const [screenError, setScreenError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);

  const [loginForm, setLoginForm] = useState({ username: "staff1", password: "" });
  const [staffForm, setStaffForm] = useState({
    housingBlock: "",
    roomNumber: "",
    collectionDate: getToday(),
  });
  const [wasteForm, setWasteForm] = useState({
    sourceLocation: SOURCE_LOCATIONS[0],
    wasteSubtype: DRY_SUBTYPES[0],
    quantity: "",
  });
  const [wetForm, setWetForm] = useState({
    wasteSubtype: WET_SUBTYPES[0],
    quantity: "",
    compostQuantity: "",
    biogasQuantity: "",
    notes: "",
  });
  const [compostRows, setCompostRows] = useState([{ recipient: "", quantity: "" }]);
  const [distributionType, setDistributionType] = useState<"Compost" | "Biogas">("Compost");

  const [staffCollections, setStaffCollections] = useState<PaginatedCollections | null>(null);
  const [processedEntries, setProcessedEntries] = useState<PaginatedWasteEntries | null>(null);
  const [processingTotals, setProcessingTotals] = useState<ProcessingTotals | null>(null);
  const [wetStatus, setWetStatus] = useState<WetProcessingStatus | null>(null);
  const [dashboard, setDashboard] = useState<DashboardBundle | null>(null);
  const [adminCollections, setAdminCollections] = useState<PaginatedCollections | null>(null);

  useEffect(() => {
    const restoreSession = async () => {
      try {
        const currentUser = await apiFetch<User>("/auth/me");
        setUser(currentUser);
      } catch {
        setUser(null);
      } finally {
        setSessionReady(true);
      }
    };

    void restoreSession();
  }, []);

  useEffect(() => {
    if (!user) {
      setStaffCollections(null);
      setProcessedEntries(null);
      setProcessingTotals(null);
      setWetStatus(null);
      setDashboard(null);
      setAdminCollections(null);
      return;
    }

    void refreshRoleData(user.role);
  }, [user]);

  async function refreshRoleData(role: User["role"]) {
    setScreenError("");

    try {
      if (role === "staff") {
        const collections = await apiFetch<PaginatedCollections>("/collections/my?page=1&page_size=12");
        setStaffCollections(collections);
        return;
      }

      if (role === "operator") {
        const [entries, totals, wet] = await Promise.all([
          apiFetch<PaginatedWasteEntries>("/processing/entries?page=1&page_size=12"),
          apiFetch<ProcessingTotals>("/processing/totals"),
          apiFetch<WetProcessingStatus>("/processing/status"),
        ]);
        setProcessedEntries(entries);
        setProcessingTotals(totals);
        setWetStatus(wet);
        return;
      }

      const [summary, trends, categoryBreakdown, blocks, operators, collections, entries, wet] =
        await Promise.all([
          apiFetch<{ metrics: SummaryMetric[] }>("/dashboard/summary"),
          apiFetch<TrendPoint[]>("/dashboard/trends?days=14"),
          apiFetch<CategoryBreakdownPoint[]>("/dashboard/category-breakdown"),
          apiFetch<BlockStat[]>("/dashboard/blocks"),
          apiFetch<OperatorStat[]>("/dashboard/operators"),
          apiFetch<PaginatedCollections>("/collections?page=1&page_size=50"),
          apiFetch<PaginatedWasteEntries>("/processing/entries?page=1&page_size=20"),
          apiFetch<WetProcessingStatus>("/processing/status"),
        ]);
      setDashboard({ summary, trends, categoryBreakdown, blocks, operators });
      setAdminCollections(collections);
      setProcessedEntries(entries);
      setWetStatus(wet);
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : "Unable to load data.");
    }
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setScreenError("");
    setNotice("");

    try {
      const response = await apiFetch<LoginResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify(loginForm),
      });
      setAuthToken(response.access_token);
      setUser(response.user);
      setNotice(`Signed in as ${response.user.username}.`);
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : "Login failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    setBusy(true);
    setScreenError("");
    try {
      await apiFetch<{ message: string }>("/auth/logout", { method: "POST" });
      clearAuthToken();
      setUser(null);
      setNotice("Session ended.");
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : "Logout failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleStaffSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setScreenError("");
    setNotice("");

    try {
      const blockNumber = Number(staffForm.housingBlock);
      if (!Number.isInteger(blockNumber) || blockNumber < 1 || blockNumber > 34) {
        setScreenError("Housing block number must be between 1 and 34.");
        return;
      }

      await apiFetch<CollectionRecord>("/collections", {
        method: "POST",
        body: JSON.stringify({ ...staffForm, collectionDate: getToday() }),
      });
      setNotice(`Collection recorded for ${staffForm.housingBlock}-${staffForm.roomNumber}.`);
      setStaffForm((current) => ({ ...current, roomNumber: "", collectionDate: getToday() }));
      if (user) {
        await refreshRoleData(user.role);
      }
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : "Collection could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function handleWeeklyExport() {
    setBusy(true);
    setScreenError("");
    setNotice("");

    try {
      const report = await apiDownload("/dashboard/export/weekly");
      const downloadUrl = window.URL.createObjectURL(report);
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.download = `campus-waste-weekly-report-${getToday()}.csv`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
      setNotice("Weekly analytics report exported.");
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : "Report export failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleClearOperationalData() {
    const confirmed = window.confirm(
      "Clear all staff collections, operator entries, wet processing, and compost distribution records?",
    );
    if (!confirmed) {
      return;
    }

    setBusy(true);
    setScreenError("");
    setNotice("");

    try {
      await apiFetch<{ message: string }>("/dashboard/data/operational", {
        method: "DELETE",
      });
      setNotice("Operational data cleared.");
      if (user) {
        await refreshRoleData(user.role);
      }
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : "Data could not be cleared.");
    } finally {
      setBusy(false);
    }
  }

  async function handleWasteSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setScreenError("");
    setNotice("");

    try {
      await apiFetch<WasteEntry>("/processing/waste", {
        method: "POST",
        body: JSON.stringify({
          ...wasteForm,
          wasteCategory: "Dry Waste",
          quantity: Number(wasteForm.quantity),
        }),
      });
      setNotice("Dry waste entry saved successfully.");
      setWasteForm((current) => ({ ...current, quantity: "" }));
      if (user) {
        await refreshRoleData(user.role);
      }
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : "Processing entry could not be saved.");
    } finally {
      setBusy(false);
    }
  }

  async function handleWetSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setScreenError("");
    setNotice("");

    try {
      const wetQuantity = Number(wetForm.quantity || 0);
      const compostQuantity = Number(wetForm.compostQuantity || 0);
      const biogasQuantity = Number(wetForm.biogasQuantity || 0);

      if (wetQuantity <= 0) {
        setScreenError("Enter the wet waste quantity.");
        return;
      }
      if (compostQuantity + biogasQuantity <= 0) {
        setScreenError("Enter how much wet waste went to compost or biogas.");
        return;
      }
      if (compostQuantity + biogasQuantity > wetQuantity) {
        setScreenError("Compost and biogas machine quantities cannot exceed wet waste quantity.");
        return;
      }

      await apiFetch<WasteEntry>("/processing/wet-intake", {
        method: "POST",
        body: JSON.stringify({
          wasteSubtype: wetForm.wasteSubtype,
          quantity: wetQuantity,
          compostQuantity,
          biogasQuantity,
          notes: wetForm.notes || undefined,
        }),
      });

      setNotice("Wet waste intake saved successfully.");
      setWetForm((current) => ({
        ...current,
        quantity: "",
        compostQuantity: "",
        biogasQuantity: "",
        notes: "",
      }));
      if (user) {
        await refreshRoleData(user.role);
      }
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : "Wet processing update failed.");
    } finally {
      setBusy(false);
    }
  }

  async function handleOutputDistributionSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setScreenError("");
    setNotice("");

    try {
      const entries = compostRows
        .map((row) => ({
          recipient: distributionType === "Compost" ? row.recipient.trim() : undefined,
          quantity: Number(row.quantity || 0),
        }))
        .filter((row) => row.quantity > 0 && (distributionType === "Biogas" || row.recipient));

      if (!entries.length) {
        setScreenError(
          distributionType === "Compost"
            ? "Add at least one compost recipient and quantity."
            : "Enter a biogas quantity.",
        );
        return;
      }

      await apiFetch<{ message: string }>("/processing/output-distributions", {
        method: "POST",
        body: JSON.stringify({ streamType: distributionType, entries }),
      });
      setNotice(`${distributionType} distribution saved successfully.`);
      setCompostRows([{ recipient: "", quantity: "" }]);
      if (user) {
        await refreshRoleData(user.role);
      }
    } catch (error) {
      setScreenError(error instanceof Error ? error.message : `${distributionType} distribution could not be saved.`);
    } finally {
      setBusy(false);
    }
  }

  const dryTotal =
    dashboard?.summary.metrics.find((metric) => metric.label === "Dry Waste")?.value ?? 0;
  const wetTotal =
    dashboard?.summary.metrics.find((metric) => metric.label === "Wet Waste")?.value ?? 0;

  function metricValue(label: string) {
    return dashboard?.summary.metrics.find((metric) => metric.label === label)?.value ?? 0;
  }

  if (!sessionReady) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100 text-sm text-slate-600">
        Loading system…
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-100 text-slate-900">
      <header className="border-b border-slate-200 bg-[linear-gradient(135deg,#0f2743_0%,#163655_100%)] text-white">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-6 py-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-300">
              Institute Sanitation Operations
            </p>
            <h1 className="mt-2 text-3xl font-semibold">Campus Waste Management System</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-200">
              Structured collection, quantification, and processing records for campus waste operations.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <div className="rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm font-medium">
              {user ? `${user.role.toUpperCase()} ACCESS` : "AUTH REQUIRED"}
            </div>
            {user ? (
              <>
                <button
                  type="button"
                  onClick={() => void refreshRoleData(user.role)}
                  className="rounded-full border border-white/20 bg-white/10 px-4 py-2 text-sm font-medium text-white transition hover:bg-white/15"
                >
                  Refresh Data
                </button>
                <button
                  type="button"
                  onClick={() => void handleLogout()}
                  className="rounded-full border border-white bg-white px-4 py-2 text-sm font-semibold text-slate-900 transition hover:bg-slate-100"
                >
                  Sign Out
                </button>
              </>
            ) : null}
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {screenError ? (
          <section className="mb-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
            {screenError}
          </section>
        ) : null}

        {notice ? (
          <section className="mb-6 rounded-2xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {notice}
          </section>
        ) : null}

        {!user ? (
          <section className="grid gap-6 lg:grid-cols-[1.15fr,0.85fr]">
            <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
              <SectionHeading
                eyebrow="System Access"
                title="Sign in to the operations portal"
                body="Role-based access is separated for field collection staff, waste quantification operators, and administrative oversight."
              />
              <form className="space-y-4" onSubmit={handleLogin}>
                <div>
                  <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="username">
                    Username
                  </label>
                  <input
                    id="username"
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                    value={loginForm.username}
                    onChange={(event) =>
                      setLoginForm((current) => ({ ...current, username: event.target.value }))
                    }
                    autoComplete="username"
                    list="demo-users"
                  />
                  <datalist id="demo-users">
                    <option value="staff1" />
                    <option value="staff2" />
                    <option value="staff3" />
                    <option value="operator1" />
                    <option value="admin" />
                  </datalist>
                </div>
                <div>
                  <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="password">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                    value={loginForm.password}
                    onChange={(event) =>
                      setLoginForm((current) => ({ ...current, password: event.target.value }))
                    }
                    autoComplete="current-password"
                    placeholder={
                      loginForm.username.startsWith("staff")
                        ? "Not required for staff"
                        : loginForm.username === "admin"
                          ? "admins_key"
                          : "op_key"
                    }
                  />
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
                >
                  {busy ? "Signing In…" : "Sign In"}
                </button>
              </form>
            </article>

            <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
              <SectionHeading
                eyebrow="Pilot Credentials"
                title="Demo access for role validation"
                body="These seeded accounts help validate the three operational layers while we complete the production rollout."
              />
              <div className="space-y-4">
                {[
                  ["staff1", "Staff collection entry", "No password"],
                  ["staff2", "Staff collection entry", "No password"],
                  ["staff3", "Staff collection entry", "No password"],
                  ["operator1", "Operator quantification workflow", "op_key"],
                  ["admin", "Administrative analytics", "admins_key"],
                ].map(([username, description, credential]) => (
                  <article key={username} className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <p className="text-sm font-semibold text-slate-900">{username}</p>
                        <p className="mt-1 text-sm text-slate-600">{description}</p>
                      </div>
                      <div className="rounded-full border border-slate-300 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">
                        {credential}
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </article>
          </section>
        ) : null}

        {user?.role === "staff" ? (
          <section className="grid gap-6 xl:grid-cols-[0.95fr,1.05fr]">
            <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
              <SectionHeading
                eyebrow="Staff Workflow"
                title="Record housing collection"
                body="Field staff records whether waste has been collected from a housing room. Quantification is handled later by the operator team."
              />
              <form className="space-y-4" onSubmit={handleStaffSubmit}>
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="housing-block">
                      Housing Block Number
                    </label>
                    <input
                      id="housing-block"
                      type="number"
                      min="1"
                      max="34"
                      step="1"
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={staffForm.housingBlock}
                      placeholder="1 to 34"
                      required
                      onChange={(event) =>
                        setStaffForm((current) => ({ ...current, housingBlock: event.target.value }))
                      }
                      onBlur={() =>
                        setStaffForm((current) => ({ ...current, housingBlock: current.housingBlock.trim() }))
                      }
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="room-number">
                      Apartment Number
                    </label>
                    <input
                      id="room-number"
                      type="text"
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={staffForm.roomNumber}
                      placeholder="Enter apartment number"
                      maxLength={32}
                      pattern="[A-Za-z0-9][A-Za-z0-9 /-]*"
                      title="Use letters, numbers, spaces, hyphens, or slashes."
                      required
                      onChange={(event) =>
                        setStaffForm((current) => ({ ...current, roomNumber: event.target.value }))
                      }
                      onBlur={() =>
                        setStaffForm((current) => ({ ...current, roomNumber: current.roomNumber.trim() }))
                      }
                    />
                  </div>
                </div>
                <div>
                  <p className="mb-2 block text-sm font-medium text-slate-700">
                    Collection Date
                  </p>
                  <div className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700">
                    {formatDateInput(getToday())}
                  </div>
                </div>
                <button
                  type="submit"
                  disabled={busy}
                  className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
                >
                  {busy ? "Saving…" : "Mark As Collected"}
                </button>
              </form>
            </article>

            <article className="rounded-3xl border border-slate-200 bg-white p-7 shadow-sm">
              <SectionHeading
                eyebrow="Recent Activity"
                title="Latest collection records"
                body="These entries remain stored in the operational database for downstream processing and weekly reporting."
              />
              <DataTable
                headers={["Date", "Block", "Apartment", "Status", "Recorded At"]}
                rows={(staffCollections?.items ?? []).map((item) => [
                  formatDate(item.collection_date),
                  item.housing_block,
                  item.room_number,
                  item.status,
                  formatDateTime(item.created_at),
                ])}
                emptyMessage="No collections have been recorded yet."
              />
            </article>
          </section>
        ) : null}

        {user?.role === "operator" ? (
          <>
            <section className="grid gap-4 md:grid-cols-3">
              <MetricCard
                label="My Entries"
                value={processingTotals?.entries_count ?? 0}
              />
              <MetricCard
                label="My Total Waste"
                value={formatWeight(processingTotals?.total_weight ?? 0)}
              />
              <MetricCard
                label="My Dry / Wet Split"
                value={`${formatWeight(processingTotals?.dry_weight ?? 0)} / ${formatWeight(
                  processingTotals?.wet_weight ?? 0,
                )}`}
              />
            </section>

            <section className="mt-6 grid gap-6 xl:grid-cols-[1.1fr,0.9fr]">
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Operator Workflow"
                  title="Record dry waste by source"
                />
                <form className="space-y-4" onSubmit={handleWasteSubmit}>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="source-location">
                      Source Location
                    </label>
                    <select
                      id="source-location"
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={wasteForm.sourceLocation}
                      onChange={(event) =>
                        setWasteForm((current) => ({ ...current, sourceLocation: event.target.value }))
                      }
                    >
                      {SOURCE_LOCATIONS.map((location) => (
                        <option key={location} value={location}>
                          {location}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="waste-subtype">
                      Dry Waste Type
                    </label>
                    <select
                      id="waste-subtype"
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={wasteForm.wasteSubtype}
                      onChange={(event) =>
                        setWasteForm((current) => ({ ...current, wasteSubtype: event.target.value }))
                      }
                    >
                      {DRY_SUBTYPES.map((item) => (
                        <option key={item} value={item}>
                          {item}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="quantity">
                      Quantity (kg)
                    </label>
                    <input
                      id="quantity"
                      type="number"
                      step="0.01"
                      min="0.01"
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={wasteForm.quantity}
                      required
                      onChange={(event) =>
                        setWasteForm((current) => ({ ...current, quantity: event.target.value }))
                      }
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={busy || !wasteForm.sourceLocation}
                    className="w-full rounded-2xl bg-slate-900 px-4 py-3 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-400"
                  >
                    {busy ? "Saving…" : "Save Dry Waste Entry"}
                  </button>
                </form>
              </article>

              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Wet Processing"
                  title="Record wet waste intake"
                />
                <form className="space-y-4" onSubmit={handleWetSubmit}>
                  <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
                    <p className="font-semibold text-slate-900">Wet processed</p>
                    <p className="mt-2 text-xl font-semibold text-slate-900">
                      {formatWeight(wetStatus?.total_wet_processed ?? 0)}
                    </p>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="wet-subtype">
                        Wet Waste Type
                      </label>
                      <select
                        id="wet-subtype"
                        className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                        value={wetForm.wasteSubtype}
                        onChange={(event) =>
                          setWetForm((current) => ({ ...current, wasteSubtype: event.target.value }))
                        }
                      >
                        {WET_SUBTYPES.map((item) => (
                          <option key={item} value={item}>
                            {item}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="wet-quantity">
                        Wet Quantity (kg)
                      </label>
                      <input
                        id="wet-quantity"
                        type="number"
                        step="0.01"
                        min="0.01"
                        className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                        value={wetForm.quantity}
                        required
                        onChange={(event) =>
                          setWetForm((current) => ({ ...current, quantity: event.target.value }))
                        }
                      />
                    </div>
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="compost-quantity">
                      Sent To Compost Machine (kg)
                    </label>
                    <input
                      id="compost-quantity"
                      type="number"
                      step="0.01"
                      min="0.01"
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={wetForm.compostQuantity}
                      onChange={(event) =>
                        setWetForm((current) => ({ ...current, compostQuantity: event.target.value }))
                      }
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="biogas-quantity">
                      Sent To Biogas Machine (kg)
                    </label>
                    <input
                      id="biogas-quantity"
                      type="number"
                      step="0.01"
                      min="0"
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={wetForm.biogasQuantity}
                      onChange={(event) =>
                        setWetForm((current) => ({ ...current, biogasQuantity: event.target.value }))
                      }
                    />
                  </div>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="wet-notes">
                      Notes
                    </label>
                    <textarea
                      id="wet-notes"
                      rows={4}
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={wetForm.notes}
                      onChange={(event) =>
                        setWetForm((current) => ({ ...current, notes: event.target.value }))
                      }
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={
                      busy ||
                      !wetForm.quantity ||
                      (!wetForm.compostQuantity && !wetForm.biogasQuantity)
                    }
                    className="w-full rounded-2xl bg-emerald-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:bg-emerald-300"
                  >
                    {busy ? "Saving…" : "Save Wet Waste Entry"}
                  </button>
                </form>
                {wetStatus?.latest_update ? (
                  <div className="mt-5 grid gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-4 text-sm text-slate-700 md:grid-cols-3">
                    <p><span className="font-semibold text-slate-900">Compost:</span> {formatWeight(wetStatus.latest_update.compost_quantity)}</p>
                    <p><span className="font-semibold text-slate-900">Biogas:</span> {formatWeight(wetStatus.latest_update.biogas_quantity)}</p>
                    <p><span className="font-semibold text-slate-900">At:</span> {formatDateTime(wetStatus.latest_update.created_at)}</p>
                  </div>
                ) : null}
              </article>
            </section>

            <section className="mt-6">
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Output Distribution"
                  title="Record compost or biogas issued"
                />
                <form className="space-y-4" onSubmit={handleOutputDistributionSubmit}>
                  <div>
                    <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="distribution-type">
                      Distribution Type
                    </label>
                    <select
                      id="distribution-type"
                      className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                      value={distributionType}
                      onChange={(event) => {
                        const nextType = event.target.value as "Compost" | "Biogas";
                        setDistributionType(nextType);
                        setCompostRows((current) =>
                          nextType === "Biogas"
                            ? [{ recipient: "", quantity: current[0]?.quantity ?? "" }]
                            : current,
                        );
                      }}
                    >
                      <option value="Compost">Compost Exit</option>
                      <option value="Biogas">Biogas Exit</option>
                    </select>
                  </div>
                  {distributionType === "Biogas" ? (
                    <div>
                      <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor="biogas-exit-quantity">
                        Biogas Quantity (kg)
                      </label>
                      <input
                        id="biogas-exit-quantity"
                        type="number"
                        step="0.01"
                        min="0.01"
                        className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                        value={compostRows[0]?.quantity ?? ""}
                        onChange={(event) =>
                          setCompostRows([{ recipient: "", quantity: event.target.value }])
                        }
                      />
                    </div>
                  ) : (
                    compostRows.map((row, index) => (
                      <div key={index} className="grid gap-4 md:grid-cols-[1fr,12rem,auto]">
                      <div>
                        <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor={`recipient-${index}`}>
                          Recipient
                        </label>
                        <input
                          id={`recipient-${index}`}
                          type="text"
                          className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                          value={row.recipient}
                          placeholder="Workers, gardeners, department"
                          onChange={(event) =>
                            setCompostRows((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index ? { ...item, recipient: event.target.value } : item,
                              ),
                            )
                          }
                        />
                      </div>
                      <div>
                        <label className="mb-2 block text-sm font-medium text-slate-700" htmlFor={`compost-row-${index}`}>
                          Quantity (kg)
                        </label>
                        <input
                          id={`compost-row-${index}`}
                          type="number"
                          step="0.01"
                          min="0.01"
                          className="w-full rounded-2xl border border-slate-300 px-4 py-3 text-sm outline-none transition focus:border-slate-500"
                          value={row.quantity}
                          onChange={(event) =>
                            setCompostRows((current) =>
                              current.map((item, itemIndex) =>
                                itemIndex === index ? { ...item, quantity: event.target.value } : item,
                              ),
                            )
                          }
                        />
                      </div>
                      <div className="flex items-end">
                        <button
                          type="button"
                          disabled={compostRows.length === 1}
                          onClick={() =>
                            setCompostRows((current) => current.filter((_, itemIndex) => itemIndex !== index))
                          }
                          className="rounded-2xl border border-slate-300 px-4 py-3 text-sm font-semibold text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-300"
                        >
                          Remove
                        </button>
                      </div>
                      </div>
                    ))
                  )}
                  <div className="flex flex-wrap gap-3">
                    {distributionType === "Compost" ? (
                      <button
                        type="button"
                        onClick={() => setCompostRows((current) => [...current, { recipient: "", quantity: "" }])}
                        className="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-50"
                      >
                        Add Recipient
                      </button>
                    ) : null}
                    <button
                      type="submit"
                      disabled={busy}
                      className="rounded-2xl bg-emerald-700 px-4 py-3 text-sm font-semibold text-white transition hover:bg-emerald-600 disabled:cursor-not-allowed disabled:bg-emerald-300"
                    >
                      {busy ? "Saving…" : `Save ${distributionType} Distribution`}
                    </button>
                  </div>
                </form>
                {(wetStatus?.latest_distributions ?? []).length ? (
                  <div className="mt-6">
                    <DataTable
                      headers={["Date", "Type", "Recipient", "Qty", "Recorded By"]}
                      rows={(wetStatus?.latest_distributions ?? []).map((item) => [
                        formatDate(item.distribution_date),
                        item.stream_type,
                        item.recipient,
                        formatWeight(item.quantity),
                        item.employee_id,
                      ])}
                      emptyMessage="No output distribution has been recorded yet."
                    />
                  </div>
                ) : null}
              </article>
            </section>

            <section className="mt-6">
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Processed Records"
                  title="My latest quantification entries"
                />
                <DataTable
                  headers={["Processed At", "Source", "Category", "Subtype", "Qty"]}
                  rows={(processedEntries?.items ?? []).map((item) => [
                    formatDateTime(item.created_at),
                    item.housing_block,
                    item.waste_category,
                    item.waste_subtype,
                    formatWeight(item.quantity),
                  ])}
                  emptyMessage="No quantification entries have been recorded yet."
                />
              </article>
            </section>
          </>
        ) : null}

        {user?.role === "admin" ? (
          <>
            <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                <SectionHeading
                  eyebrow="Administrative Dashboard"
                  title="Operational analytics and oversight"
                />
                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={() => void handleWeeklyExport()}
                    disabled={busy}
                    className="rounded-2xl border border-slate-300 bg-white px-4 py-3 text-sm font-semibold text-slate-900 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:text-slate-400"
                  >
                    Export Last 7 Days
                  </button>
                  <button
                    type="button"
                    onClick={() => void handleClearOperationalData()}
                    disabled={busy}
                    className="rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700 transition hover:bg-rose-100 disabled:cursor-not-allowed disabled:text-rose-300"
                  >
                    Clear Records
                  </button>
                </div>
              </div>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                <MetricCard label="Collections Today" value={metricValue("Collections Today")} />
                <MetricCard label="Collections This Week" value={metricValue("Collections This Week")} />
                <MetricCard
                  label="Waste Processed Today"
                  value={formatWeight(metricValue("Waste Processed Today"))}
                />
                <MetricCard
                  label="Waste Processed This Week"
                  value={formatWeight(metricValue("Waste Processed This Week"))}
                />
                <MetricCard label="Staff Collection Records" value={metricValue("Staff Collection Records")} />
              </div>
            </section>

            <section className="mt-6 grid gap-6 xl:grid-cols-[1.35fr,0.85fr]">
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Trend Analysis"
                  title="Daily processed waste"
                />
                {dashboard?.trends.length ? (
                  <Line
                    data={{
                      labels: dashboard.trends.map((point) => point.date),
                      datasets: [
                        {
                          label: "Processed Weight (kg)",
                          data: dashboard.trends.map((point) => point.total_weight),
                          borderColor: "#143656",
                          backgroundColor: "rgba(20, 54, 86, 0.12)",
                          fill: true,
                          tension: 0.32,
                        },
                      ],
                    }}
                    options={{ plugins: { legend: { display: false } } }}
                  />
                ) : (
                  <EmptyState message="Trend data will appear once operator processing begins." />
                )}
              </article>

              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading eyebrow="Waste Mix" title="Dry and wet split by period" />
                {(dashboard?.categoryBreakdown ?? []).length ? (
                  <div className="space-y-4">
                    {dashboard?.categoryBreakdown.map((period) => (
                      <article
                        key={period.label}
                          className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">
                              {period.label}
                            </p>
                            <p className="mt-2 text-lg font-semibold text-slate-900">
                              {formatWeight(period.dry_weight + period.wet_weight)}
                            </p>
                          </div>
                          <div className="text-right text-sm text-slate-600">
                            <p>Dry: {formatWeight(period.dry_weight)}</p>
                            <p className="mt-1">Wet: {formatWeight(period.wet_weight)}</p>
                          </div>
                        </div>
                      </article>
                    ))}
                    {(Number(dryTotal) || Number(wetTotal)) ? (
                      <Doughnut
                        data={{
                          labels: ["Dry Waste", "Wet Waste"],
                          datasets: [
                            {
                              data: [Number(dryTotal), Number(wetTotal)],
                              backgroundColor: ["#143656", "#3f7d5a"],
                            },
                          ],
                        }}
                        options={{ plugins: { legend: { position: "bottom" } } }}
                      />
                    ) : null}
                  </div>
                ) : (
                  <EmptyState message="Distribution data will appear after operator records are saved." />
                )}
              </article>
            </section>

            <section className="mt-6 grid gap-6 xl:grid-cols-2">
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Source Analytics"
                  title="Processed weight by source location"
                />
                {dashboard?.blocks.length ? (
                  <Bar
                    data={{
                      labels: dashboard.blocks.map((item) => item.housing_block),
                      datasets: [
                        {
                          label: "Processed Weight (kg)",
                          data: dashboard.blocks.map((item) => item.processed_weight),
                          backgroundColor: "#143656",
                        },
                      ],
                    }}
                    options={{ plugins: { legend: { display: false } } }}
                  />
                ) : (
                  <EmptyState message="Source analytics will populate after recorded processing." />
                )}
              </article>

              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Operator Performance"
                  title="Quantification throughput"
                />
                {(dashboard?.operators ?? []).length ? (
                  <div className="space-y-4">
                    {dashboard?.operators.map((operator) => (
                      <article
                        key={operator.employee_id}
                        className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3"
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="font-semibold text-slate-900">{operator.employee_id}</p>
                            <p className="mt-1 text-sm text-slate-600">
                              {operator.entries_count} entries processed
                            </p>
                          </div>
                          <div className="text-right">
                            <p className="text-xs uppercase tracking-[0.18em] text-slate-500">
                              Total Weight
                            </p>
                            <p className="mt-1 text-lg font-semibold text-slate-900">
                              {formatWeight(operator.total_weight)}
                            </p>
                          </div>
                        </div>
                      </article>
                    ))}
                  </div>
                ) : (
                  <EmptyState message="Operator statistics will appear after quantification entries are recorded." />
                )}
              </article>
            </section>

            <section className="mt-6 grid gap-6 xl:grid-cols-[0.95fr,1.05fr]">
              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Worker Reports"
                  title="Individual staff collection records"
                />
                <DataTable
                  headers={["Date", "Block", "Apartment", "Staff", "Status"]}
                  rows={(adminCollections?.items ?? []).map((item) => [
                    formatDate(item.collection_date),
                    item.housing_block,
                    item.room_number,
                    item.employee_id,
                    item.status,
                  ])}
                  emptyMessage="No collections are available yet."
                  maxHeightClass="max-h-[32rem]"
                />
              </article>

              <article className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
                <SectionHeading
                  eyebrow="Operator Records"
                  title="Latest quantification entries"
                />
                <DataTable
                  headers={["Processed At", "Source", "Category", "Subtype", "Qty"]}
                  rows={(processedEntries?.items ?? []).map((item) => [
                    formatDateTime(item.created_at),
                    item.room_number === "Direct" ? item.housing_block : `${item.housing_block}-${item.room_number}`,
                    item.waste_category,
                    item.waste_subtype,
                    formatWeight(item.quantity),
                  ])}
                  emptyMessage="No processing entries are available yet."
                  maxHeightClass="max-h-[32rem]"
                />
              </article>
            </section>

            <section className="mt-6 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <SectionHeading
                eyebrow="Wet Processing Status"
                title="Compost and biogas status"
              />
              {wetStatus?.latest_update ? (
                <div className="grid gap-4 md:grid-cols-4">
                  <MetricCard label="Wet Waste Processed" value={formatWeight(wetStatus.total_wet_processed)} />
                  <MetricCard
                    label="Compost Deposited"
                    value={formatWeight(wetStatus.compost_deposited)}
                  />
                  <MetricCard
                    label="Biogas Deposited"
                    value={formatWeight(wetStatus.biogas_deposited)}
                  />
                  <MetricCard
                    label="Last Updated"
                    value={formatDateTime(wetStatus.latest_update.created_at)}
                  />
                </div>
              ) : (
                <EmptyState message="No wet processing update has been recorded yet." />
              )}
            </section>
          </>
        ) : null}
      </main>
    </div>
  );
}
