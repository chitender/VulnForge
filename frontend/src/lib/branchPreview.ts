/**
 * Client-side branch name preview — mirrors backend resolve_branch() logic.
 * Substitutes {image}, {tag}, {date}, {version}, {scan_id} placeholders.
 * Unknown placeholders are left as-is (shown literally in the preview).
 */
export function resolveBranchPreview(
  template: string,
  vars: Record<string, string>,
): string {
  if (!template.trim()) return ''
  let result = template
  for (const [key, value] of Object.entries(vars)) {
    const safe = key === 'image' ? value.replace(/\//g, '-') : value
    result = result.split(`{${key}}`).join(safe)
  }
  return result
}
