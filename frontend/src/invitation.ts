// Remove the fragment synchronously before any API effect can run.
export function captureInvite() {
  let token = "";
  if (location.pathname === "/invite") {
    const params = new URLSearchParams(location.hash.slice(1));
    const values = params.getAll("token");
    if (
      values.length === 1 &&
      [...params.keys()].length === 1 &&
      /^[A-Za-z0-9_-]{20,256}$/.test(values[0])
    )
      token = values[0];
    history.replaceState(null, "", location.pathname + location.search);
  }
  return token;
}
