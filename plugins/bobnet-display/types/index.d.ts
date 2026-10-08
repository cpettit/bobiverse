// State contract for the Bobnet display mod.

export type BobStatus =
  | "spooling"
  | "running"
  | "reporting"
  | "done"
  | "aborted"
  | "denied";

export type Bob = {
  agentId: string;
  /** agent type without plugin prefix: "garfield", "thoth", "general-purpose" */
  name: string;
  /** short task label from the Agent tool's description */
  task: string;
  status: BobStatus;
  startedAt: number;
  endedAt?: number;
  toolCount: number;
  /** the most recent tool call, e.g. "Edit src/api.py" */
  lastTool?: string;
  /** did the subagent's report include a DRIFT CHECK section (the drift hook asks for one) */
  driftChecked?: boolean;
};

export type Traffic = {
  at: number;
  /** who: a Bob's name, "BUSTERS", "SUDDAR", "PRIME", "ORACLE", or "BOB" for the main loop */
  from: string;
  text: string;
  tone: "normal" | "warn" | "alert" | "dim";
};

export type GateCounts = { asks: number; denies: number };

declare module "claude-code" {
  interface PluginState {
    "bobnet-display": {
      bobs: Bob[];
      traffic: Traffic[];
      gates: Record<"busters" | "suddar" | "prime" | "oracle", GateCounts>;
      /** when the current moot started (first Bob of a burst spawned); null when idle */
      mootStartedAt: number | null;
    };
  }
}
