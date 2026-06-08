"use client";

import { useCallback, useEffect, useState } from "react";

type Event = {
  id: number;
  title: string;
  description?: string;
  event_type: string;
  start_time?: string;
  end_time?: string;
  location?: string;
  source: string;
  metadata?: Record<string, unknown>;
};

type GroupInfo = {
  code: string;
  name: string;
  party_leader_email: string;
  members: string[];
  events: Event[];
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  (typeof window !== "undefined"
    ? `${window.location.protocol}//${window.location.hostname}:8000`
    : "http://localhost:8000");

function getInitialGroupCode() {
  if (typeof window === "undefined") {
    return "";
  }
  return new URLSearchParams(window.location.search).get("group_code") || "";
}

export default function SyncUpApp() {
  const [initialGroupCode] = useState(getInitialGroupCode);
  const [partyName, setPartyName] = useState("");
  const [groupCode, setGroupCode] = useState(initialGroupCode);
  const [groupInfo, setGroupInfo] = useState<GroupInfo | null>(null);
  const [message, setMessage] = useState(
    initialGroupCode ? "Party created. Share this code with your group." : "",
  );
  const [isLoading, setIsLoading] = useState(false);

  const fetchGroup = useCallback(async (code: string) => {
    if (!code) {
      setMessage("Enter a party code to view the calendar.");
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/groups/${encodeURIComponent(code)}`);
      if (!res.ok) {
        throw new Error("Unable to load party");
      }
      const data: GroupInfo = await res.json();
      setGroupInfo(data);
      setGroupCode(data.code);
      setMessage("");
    } catch {
      setMessage("Could not find party. Please verify the code.");
      setGroupInfo(null);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (initialGroupCode) {
      const timeoutId = window.setTimeout(() => {
        void fetchGroup(initialGroupCode);
      }, 0);

      return () => window.clearTimeout(timeoutId);
    }
  }, [fetchGroup, initialGroupCode]);

  const createParty = async () => {
    const params = new URLSearchParams();
    if (partyName) params.set("party_name", partyName);
    const res = await fetch(`${API_BASE}/auth/google/url?${params.toString()}`);
    if (res.ok) {
      const data = await res.json();
      window.location.href = data.authorization_url;
    } else {
      setMessage(
        "Could not start Google sign-in. Check backend configuration.",
      );
    }
  };

  const refreshBookings = async () => {
    if (!groupCode) {
      setMessage("Enter the party code to refresh bookings.");
      return;
    }
    setIsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/sync`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ group_code: groupCode }),
      });
      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}));
        throw new Error(errorData.detail || "Sync failed");
      }
      const data = await res.json();
      setMessage(
        `Refreshed ${data.synced_messages} emails and upserted ${data.events_upserted} events.`,
      );
      fetchGroup(groupCode);
    } catch (error) {
      setMessage(
        error instanceof Error ? error.message : "Unable to refresh bookings.",
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-5xl px-6 py-12">
        <div className="mb-10 rounded-3xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="text-4xl font-semibold">SyncUp</h1>
          <p className="mt-3 text-slate-600">
            A shared travel planner where the party leader links Gmail and
            everyone else views by code.
          </p>
        </div>

        <div className="grid gap-8 lg:grid-cols-2">
          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-2xl font-semibold">
              Party leader: Connect Gmail
            </h2>
            <p className="mt-2 text-slate-600">
              Only the party leader needs Google access. This creates the shared
              party and syncs booking emails.
            </p>
            <label className="mt-4 block text-sm font-medium text-slate-700">
              Party name
            </label>
            <input
              className="mt-2 w-full rounded-2xl border border-slate-300 p-3"
              value={partyName}
              placeholder="Weekend trip"
              onChange={(event) => setPartyName(event.target.value)}
            />
            <button
              onClick={createParty}
              disabled={isLoading}
              className="mt-4 inline-flex items-center justify-center rounded-2xl bg-slate-900 px-5 py-3 text-white hover:bg-slate-800"
            >
              {isLoading ? "Working..." : "Connect Gmail and create party"}
            </button>
            <div className="mt-4 rounded-2xl bg-slate-50 p-4 text-sm text-slate-700">
              After sign-in, your party code will be visible. Share it with your
              friends so they can view the calendar.
            </div>
          </section>

          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="text-2xl font-semibold">Member: View by code</h2>
            <p className="mt-2 text-slate-600">
              Enter the party code below and see the shared calendar instantly.
              No email or login required.
            </p>
            <label className="mt-4 block text-sm font-medium text-slate-700">
              Party code
            </label>
            <input
              className="mt-2 w-full rounded-2xl border border-slate-300 p-3"
              value={groupCode}
              placeholder="ABC123"
              onChange={(event) => setGroupCode(event.target.value)}
            />
            <button
              onClick={() => fetchGroup(groupCode)}
              disabled={isLoading}
              className="mt-4 inline-flex items-center justify-center rounded-2xl bg-slate-900 px-5 py-3 text-white hover:bg-slate-800"
            >
              {isLoading ? "Loading..." : "View party calendar"}
            </button>
          </section>
        </div>

        <section className="mt-10 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-2xl font-semibold">Refresh shared bookings</h2>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <input
              className="rounded-2xl border border-slate-300 p-3"
              value={groupCode}
              placeholder="Party code"
              onChange={(event) => setGroupCode(event.target.value)}
            />
            <button
              onClick={refreshBookings}
              disabled={isLoading}
              className="inline-flex min-w-[120px] items-center justify-center rounded-2xl bg-slate-700 px-5 py-3 text-white hover:bg-slate-600"
            >
              {isLoading ? "Refreshing..." : "Refresh bookings"}
            </button>
          </div>
          <p className="mt-3 text-sm text-slate-500">
            Only the party leader can successfully refresh bookings; this just
            triggers the sync by code.
          </p>
        </section>

        {groupInfo ? (
          <section className="mt-10 rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
            <div className="grid gap-5 lg:grid-cols-2">
              <div className="rounded-3xl bg-slate-50 p-5">
                <p className="text-sm text-slate-500">Party</p>
                <p className="mt-2 text-xl font-semibold">{groupInfo.name}</p>
                <p className="mt-1 text-slate-600">Code: {groupInfo.code}</p>
                <p className="mt-1 text-slate-600">
                  Party leader: {groupInfo.party_leader_email}
                </p>
                <p className="mt-4 text-sm text-slate-500">Members</p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-slate-700">
                  {groupInfo.members.length > 0 ? (
                    groupInfo.members.map((email) => (
                      <li key={email}>{email}</li>
                    ))
                  ) : (
                    <li>No members added yet.</li>
                  )}
                </ul>
                <a
                  className="mt-6 inline-flex items-center rounded-2xl bg-slate-900 px-5 py-3 text-sm font-medium text-white hover:bg-slate-800"
                  href={`${API_BASE}/groups/${encodeURIComponent(groupInfo.code)}/csv`}
                >
                  Download CSV
                </a>
              </div>

              <div className="rounded-3xl bg-slate-50 p-5">
                <p className="text-sm text-slate-500">Events</p>
                {groupInfo.events.length === 0 ? (
                  <p className="mt-4 text-slate-600">
                    No synced events yet. Refresh bookings from the party
                    leader.
                  </p>
                ) : (
                  <div className="mt-4 space-y-4">
                    {groupInfo.events.map((event) => (
                      <div
                        key={event.id}
                        className="rounded-2xl border border-slate-200 bg-white p-4"
                      >
                        <div className="flex items-center justify-between gap-4">
                          <h3 className="text-lg font-semibold">
                            {event.title}
                          </h3>
                          <span className="rounded-full bg-slate-100 px-3 py-1 text-xs uppercase tracking-[0.12em] text-slate-600">
                            {event.event_type}
                          </span>
                        </div>
                        <p className="mt-2 text-slate-600">
                          {event.description || "No description"}
                        </p>
                        <p className="mt-2 text-sm text-slate-500">
                          {event.start_time || "No start"} —{" "}
                          {event.end_time || "No end"}
                        </p>
                        <p className="mt-1 text-sm text-slate-500">
                          {event.location || "No location"}
                        </p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </section>
        ) : null}

        {message ? (
          <div className="mt-8 rounded-3xl bg-slate-900 px-6 py-4 text-white shadow-sm">
            {message}
          </div>
        ) : null}
      </div>
    </div>
  );
}
