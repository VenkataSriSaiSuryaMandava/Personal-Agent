import type { Provider, JobSourceInput } from "./discovery";

export const EMPLOYERS: readonly JobSourceInput[] = [
  { company: "Ashby", provider: "ashby", board: "Ashby", enabled: true },
  { company: "Discord", provider: "greenhouse", board: "discord", enabled: true },
  { company: "Greenhouse", provider: "greenhouse", board: "greenhouse", enabled: true },
  { company: "Palantir", provider: "lever", board: "palantir", enabled: true },
  { company: "Stripe", provider: "greenhouse", board: "stripe", enabled: true },
  { company: "Wealthfront", provider: "lever", board: "wealthfront", enabled: true },
];

const BOARD = /^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$/;

const HOSTS: Record<string, Provider> = {
  "boards.greenhouse.io": "greenhouse",
  "job-boards.greenhouse.io": "greenhouse",
  "jobs.lever.co": "lever",
  "jobs.ashbyhq.com": "ashby",
};

export function recognizeBoard(
  value: string,
  selectedProvider: Provider,
): { provider: Provider; board: string } {
  const input = value.trim();

  if (BOARD.test(input)) {
    return {
      provider: selectedProvider,
      board: input,
    };
  }

  if (
    input.length > 2000 ||
    !input.startsWith("https://") ||
    /[\s\\\p{Cc}\p{Cf}]/u.test(input)
  ) {
    throw new Error("Enter a valid board identifier or supported HTTPS career URL.");
  }

  const url = new URL(input);

  if (
    url.protocol !== "https:" ||
    url.username ||
    url.password ||
    url.port ||
    url.hash ||
    url.search
  ) {
    throw new Error("Use a clean employer board URL without parameters.");
  }

  const authority = input.slice(8).split("/")[0];

  if (authority !== url.hostname) {
    throw new Error("Unsupported employer URL.");
  }

  if (
    url.hostname === "stripe.com" &&
    ["/jobs/search", "/jobs/search/", "/careers", "/careers/"]
      .includes(url.pathname)
  ) {
    return {
      provider: "greenhouse",
      board: "stripe",
    };
  }

  const provider = Object.hasOwn(HOSTS, url.hostname)
    ? HOSTS[url.hostname]
    : undefined;

  if (!provider) {
    throw new Error("Career URL not supported. Use a verified employer or its board identifier.");
  }

  const match = /^\/([A-Za-z0-9][A-Za-z0-9_-]{0,99})\/?$/
    .exec(url.pathname);

  if (!match || input !== `https://${url.hostname}${url.pathname}`) {
    throw new Error("Enter the employer's main job board URL.");
  }

  return {
    provider,
    board: match[1],
  };
}
