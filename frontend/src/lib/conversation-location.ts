const KEY = "aegis-active-conversation";

const UUID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

export function readActiveConversation(): string | null {
  try {
    const value = sessionStorage.getItem(KEY);

    return value && UUID.test(value)
      ? value
      : null;
  } catch {
    return null;
  }
}

export function rememberActiveConversation(
  id: string | null,
) {
  try {
    if (id && UUID.test(id)) {
      sessionStorage.setItem(KEY, id);
    } else {
      sessionStorage.removeItem(KEY);
    }
  } catch {
    // Browser storage is optional.
  }
}
