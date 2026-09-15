// Local presentation names share the existing grade/ID portrait mapping.
// Never change trace IDs, choices, or solver results.
let names = new Map();

export function mapDirectoryStudents(simulated, directory) {
  const mapped = new Map();
  const compare = (a, b) => String(a.id).localeCompare(String(b.id), 'en');
  for (const grade of new Set(simulated.map(student => student.grade))) {
    const slots = simulated.filter(student => student.grade === grade).sort(compare);
    const people = directory.filter(student => student.grade === grade).sort(compare);
    slots.forEach((slot, index) => {
      if (people[index]) mapped.set(slot.id, people[index]);
    });
  }
  return mapped;
}

export function setDirectoryNames(mapped) {
  names = new Map([...mapped].filter(([, name]) => typeof name === 'string' && name.trim()));
}

export function displayName(id) { return names.get(id) || id; }
export function studentLabel(id) { return names.has(id) ? `${names.get(id)} (${id})` : id; }
export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
}
