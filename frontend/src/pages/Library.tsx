import { PrivateLibrary } from "./PrivateLibrary";
import { PublicLibrary } from "./PublicLibrary";

export function Library() {
  const mode = import.meta.env.VITE_MANGAVAULT_MODE;
  return mode === "private" ? <PrivateLibrary /> : <PublicLibrary />;
}
