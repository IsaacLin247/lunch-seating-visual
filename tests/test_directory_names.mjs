import assert from 'node:assert/strict';
import { mapDirectoryStudents, setDirectoryNames, displayName, studentLabel, escapeHtml } from '../docs/names.js';

const slots = [{ id: 'S003', grade: 12 }, { id: 'S002', grade: 11 }, { id: 'S001', grade: 11 }, { id: 'S004', grade: 12 }];
const directory = [
  { id: '22', grade: 11, name: 'Morgan & Lee', photoUrl: 'blob:second' },
  { id: '10', grade: 12, name: 'Casey Chen', photoUrl: 'blob:senior' },
  { id: '11', grade: 11, name: 'Alex Rivera', photoUrl: null },
  { id: '01', grade: 9, name: 'Unused Student' },
];
const before = JSON.stringify({ slots, directory });
const mapped = mapDirectoryStudents(slots, directory);
assert.equal(mapped.size, 3);
assert.equal(mapped.get('S001').name, 'Alex Rivera');
assert.equal(mapped.get('S002').photoUrl, 'blob:second');
assert.equal(mapped.get('S003').name, 'Casey Chen');
assert.equal(mapped.has('S004'), false);
assert.equal(JSON.stringify({ slots, directory }), before);
assert.deepEqual([...mapDirectoryStudents([...slots].reverse(), [...directory].reverse())], [...mapped]);

const labels = new Map([...mapped].map(([id, person]) => [id, person.name]));
setDirectoryNames(labels);
labels.set('S001', 'Changed externally');
assert.equal(displayName('S001'), 'Alex Rivera');
assert.equal(studentLabel('S002'), 'Morgan & Lee (S002)');
assert.equal(displayName('S004'), 'S004');
assert.equal(escapeHtml('<a title="x">&\'</a>'), '&lt;a title=&quot;x&quot;&gt;&amp;&#39;&lt;/a&gt;');
setDirectoryNames(new Map([['S001', 'Replacement Student']]));
assert.equal(displayName('S001'), 'Replacement Student');
assert.equal(displayName('S002'), 'S002');
setDirectoryNames(new Map());
assert.equal(studentLabel('S001'), 'S001');
console.log('Directory name mapping passed: grade identity, missing photos, stable order, escaping, replacement, and clearing.');
