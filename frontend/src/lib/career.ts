import { workspaceFetch } from "@/lib/session-client";
export type CareerProfile = {
  full_name: string;
  email: string;
  phone: string;
  location: string;
  headline: string;
  summary: string;
  skills: string[];
  education: string;
  experience: string;
  projects: string;
  target_roles: string[];
  target_locations: string[];
  work_mode: "any" | "remote" | "hybrid" | "onsite";
  employment_type:
    "any" | "full_time" | "part_time" |
    "contract" | "internship";
  work_authorization: string;
  sponsorship_required: "unknown" | "yes" | "no";
  salary_currency: string;
  salary_min: number | null;
  salary_max: number | null;
  linkedin_url: string;
  portfolio_url: string;
  github_url: string;
};

export type ProfileSnapshot = {
  profile: CareerProfile;
  revision: number;
  updated_at: number | null;
};

export type Resume = {
  id: string;
  title: string;
  media_type: string;
  size_bytes: number;
  sha256: string;
  revision: number;
  is_active: number;
  created_at: number;
  updated_at: number;
};

export type ResumeDetail = Resume & {
  extracted_text: string;
};

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

type Operation =
  | { kind: "profile" }
  | { kind: "saveProfile"; snapshot: ProfileSnapshot }
  | { kind: "list" }
  | { kind: "detail"; id: string }
  | { kind: "download"; id: string }
  | {
      kind: "upload";
      title: string;
      media_type: string;
      document: string;
    }
  | {
      kind: "mutate";
      resume: Resume;
      action: "activate" | "edit" | "delete";
      text?: string;
    };

function validId(id: string) {
  if (!UUID.test(id)) {
    throw new Error("Invalid document ID.");
  }
  return id;
}

async function request(operation: Operation) {
  let endpoint: string;
  let method: "GET" | "POST" | "PATCH" = "GET";
  let body: string | undefined;

  const query = new URLSearchParams();

  switch (operation.kind) {
    case "profile":
      endpoint = "/api/agent/career/profile";
      break;

    case "saveProfile":
      endpoint = "/api/agent/career/profile";
      method = "PATCH";
      body = JSON.stringify({
        ...operation.snapshot.profile,
        expected_revision: operation.snapshot.revision,
      });
      break;

    case "list":
      endpoint = "/api/agent/career/resumes";
      break;

    case "detail":
      endpoint = "/api/agent/career/resume";
      query.set("id", validId(operation.id));
      break;

    case "download":
      endpoint = "/api/agent/career/download";
      query.set("id", validId(operation.id));
      break;

    case "upload":
      endpoint = "/api/agent/career/resumes";
      method = "POST";
      body = JSON.stringify({
        title: operation.title,
        media_type: operation.media_type,
        document: operation.document,
      });
      break;

    case "mutate":
      endpoint = "/api/agent/career/resume";
      method = "POST";
      body = JSON.stringify({
        id: validId(operation.resume.id),
        expected_revision: operation.resume.revision,
        action: operation.action,
        ...(operation.action === "edit"
          ? { extracted_text: operation.text }
          : {}),
      });
      break;

    default:
      throw new Error("Invalid career operation.");
  }

  const url = new URL(endpoint, window.location.origin);
  url.search = query.toString();

  if (
    url.origin !== window.location.origin ||
    url.pathname !== endpoint
  ) {
    throw new Error("Invalid career endpoint.");
  }

  const response = await workspaceFetch(url, {
    method,
    body,
    headers: body === undefined
      ? undefined
      : { "Content-Type": "application/json" },
    credentials: "same-origin",
    cache: "no-store",
    redirect: "error",
    signal: AbortSignal.timeout(
      operation.kind === "upload" ? 35000 : 15000,
    ),
  });

  if (response.status === 401) {
    window.dispatchEvent(
      new Event("aegis-session-expired"),
    );
  }

  if (!response.ok) {
    const errors: Record<number, string> = {
      401: "Session expired.",
      403: "Career access denied.",
      404: "Document no longer exists.",
      409: "Record changed, duplicate upload or resume limit reached. Refresh before retrying.",
      413: "Document or request too large.",
      415: "Unsupported content type.",
      422: "Invalid fields or unsupported document.",
      429: "Document parser is busy. Try again.",
      503: "Career storage unavailable.",
    };

    throw new Error(
      errors[response.status] ?? "Career request failed.",
    );
  }

  return response;
}

export async function getProfile(): Promise<ProfileSnapshot> {
  return (await request({ kind: "profile" })).json();
}

export async function saveProfile(
  snapshot: ProfileSnapshot,
): Promise<ProfileSnapshot> {
  return (await request({
    kind: "saveProfile", snapshot,
  })).json();
}

export async function listResumes(): Promise<Resume[]> {
  const response = await request({ kind: "list" });

  const data = await response.json() as {
    resumes: Resume[];
  };

  return data.resumes;
}

export async function getResume(
  id: string,
): Promise<ResumeDetail> {
  return (await request({ kind: "detail", id })).json();
}

function readDocument(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();

    reader.onerror = () =>
      reject(new Error("Unable to read document."));

    reader.onload = () => {
      if (typeof reader.result !== "string") {
        reject(new Error("Invalid document."));
        return;
      }

      const index = reader.result.indexOf(",");

      if (index < 0) {
        reject(new Error("Invalid document."));
        return;
      }

      resolve(reader.result.slice(index + 1));
    };

    reader.readAsDataURL(file);
  });
}

export async function uploadResume(
  file: File,
  title: string,
): Promise<ResumeDetail> {
  if (file.size < 1 || file.size > 10 * 1024 * 1024) {
    throw new Error("Choose a document of up to 10 MiB.");
  }

  const extension = file.name.split(".").pop()?.toLowerCase();

  const formats: Record<string, string> = {
    pdf: "application/pdf",
    docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    txt: "text/plain",
  };

  const media_type = formats[extension ?? ""];

  if (!media_type) {
    throw new Error("Choose PDF, DOCX or TXT.");
  }

  const document = await readDocument(file);

  return (await request({
    kind: "upload",
    title,
    media_type,
    document,
  })).json();
}

export async function mutateResume(
  resume: Resume,
  action: "activate" | "edit" | "delete",
  text?: string,
) {
  return (await request({
    kind: "mutate",
    resume,
    action,
    text,
  })).json();
}

export async function downloadResume(
  resume: Resume,
  allowed: () => boolean,
) {
  const response = await request({
    kind: "download",
    id: resume.id,
  });

  const blob = await response.blob();

  if (!allowed()) return;

  const extension =
    resume.media_type === "application/pdf" ? "pdf" :
    resume.media_type === "text/plain" ? "txt" : "docx";

  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");

  anchor.href = url;
  anchor.download = `resume-${resume.id}.${extension}`;

  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  window.setTimeout(
    () => URL.revokeObjectURL(url),
    1000,
  );
}
