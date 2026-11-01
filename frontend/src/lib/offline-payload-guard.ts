/** Garde-fou défensif : refuser les secrets connus dans les futures charges hors ligne. */
const FORBIDDEN = /(?:token|password|passwd|secret|authorization|cookie|api[_-]?key|credential|private[_-]?key)/i;

export function assertOfflinePayloadSafe(value: unknown): void {
  const visited = new WeakSet<object>();
  function visit(node: unknown, depth: number): void {
    if (depth > 16) throw new Error("Opération hors ligne trop imbriquée");
    if (node === null || typeof node !== "object") return;
    if (visited.has(node)) throw new Error("Référence circulaire interdite");
    visited.add(node);
    if (Array.isArray(node)) {
      node.forEach((item) => visit(item, depth + 1));
      return;
    }
    if (Object.getPrototypeOf(node) !== Object.prototype) {
      throw new Error("Seuls les objets JSON ordinaires sont acceptés");
    }
    for (const [key, child] of Object.entries(node)) {
      if (FORBIDDEN.test(key)) throw new Error("Champ sensible interdit hors ligne");
      visit(child, depth + 1);
    }
  }
  visit(value, 0);
}
