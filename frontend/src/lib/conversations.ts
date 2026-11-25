import { workspaceFetch } from "@/lib/session-client";
export type ConversationSummary = {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
};

export type ConversationDetail =
  ConversationSummary & {
    turns: {
      user: string;
      assistant: string;
      created_at: number;
    }[];
  };

export type ConversationPage = {
  conversations: ConversationSummary[];
  next_offset: number | null;
};

const BASE = "/api/agent/conversations";

export function validConversationId(
  value: unknown,
): value is string {
  return typeof value === "string" &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(value);
}

function validSummary(
  value: ConversationSummary,
) {
  return Boolean(
    value &&
    validConversationId(value.id) &&
    typeof value.title === "string" &&
    value.title.trim() &&
    value.title.length <= 240 &&
    Number.isSafeInteger(value.created_at) &&
    Number.isSafeInteger(value.updated_at)
  );
}

async function request<T>(
  suffix = "",
  init: RequestInit = {},
): Promise<T> {
  const response = await workspaceFetch(
    BASE + suffix,
    {
      ...init,
      credentials: "same-origin",
      cache: "no-store",
      signal: AbortSignal.timeout(15000),
    },
  );

  if (response.status === 401) {
    window.dispatchEvent(
      new Event("aegis-session-expired"),
    );
  }

  if (!response.ok) {
    throw new Error(
      response.status === 404
        ? "Conversation no longer exists."
        : "Unable to access conversation history.",
    );
  }

  return response.json() as Promise<T>;
}

function route(id: string) {
  if (!validConversationId(id)) {
    throw new Error("Invalid conversation ID.");
  }

  return "/" + id;
}

export async function listConversations(offset = 0) {
  const result = await request<ConversationPage>(
    "?limit=50&offset=" + offset,
  );

  if (
    !Array.isArray(result.conversations) ||
    !result.conversations.every(validSummary) ||
    (
      result.next_offset !== null &&
      (
        !Number.isSafeInteger(result.next_offset) ||
        result.next_offset <= offset
      )
    )
  ) {
    throw new Error("Invalid history response.");
  }

  return result;
}

export async function openConversation(id: string) {
  const result = await request<ConversationDetail>(
    route(id),
  );

  if (
    !validSummary(result) ||
    result.id !== id ||
    !Array.isArray(result.turns) ||
    !result.turns.every(turn =>
      turn &&
      typeof turn.user === "string" &&
      typeof turn.assistant === "string"
    )
  ) {
    throw new Error("Invalid saved conversation.");
  }

  return result;
}

export async function renameConversation(
  id: string,
  title: string,
) {
  return request<ConversationSummary>(
    route(id),
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ title }),
    },
  );
}

export async function deleteConversation(id: string) {
  const result = await request<{ deleted: boolean }>(
    route(id),
    { method: "DELETE" },
  );

  if (result.deleted !== true) {
    throw new Error("Unable to delete conversation.");
  }
}
