// Focused avatar mapping checks; run with node tests/test_avatar_mapping.mjs.
import assert from 'node:assert/strict';
import {
  anonymousAvatarUri,
  avatarBitmap,
  avatarImg,
  avatarUri,
  clearDirectoryPortraits,
  directoryPortraitUri,
  setDirectoryPortraits,
} from '../docs/avatars.js';

const images = [];
class FakeImage {
  constructor() {
    this.className = '';
    this.classList = {
      add: (value) => { this.className = [...new Set([...this.className.split(' ').filter(Boolean), value])].join(' '); },
      remove: (value) => { this.className = this.className.split(' ').filter((item) => item !== value).join(' '); },
      contains: (value) => this.className.split(' ').includes(value),
    };
    images.push(this);
  }
  getAttribute(name) { return this[name] ?? null; }
}

globalThis.Image = FakeImage;
globalThis.document = {
  createElement: (tag) => tag === 'img' ? new FakeImage() : { dataset: {}, width: 0, height: 0 },
};

clearDirectoryPortraits();
const anonymous = anonymousAvatarUri('S001');
assert.match(anonymous, /^data:image\/svg\+xml/);
assert.equal(avatarUri('S001'), anonymous);
assert.equal(directoryPortraitUri('S001'), null);

const mapping = new Map([['S001', 'blob:https://school.example/portrait-a']]);
assert.equal(setDirectoryPortraits(mapping), 1);
mapping.set('S001', 'blob:https://school.example/caller-mutation');
mapping.set('S002', 'blob:https://school.example/new-entry');
assert.equal(directoryPortraitUri('S001'), 'blob:https://school.example/portrait-a');
assert.equal(directoryPortraitUri('S002'), null);
assert.equal(avatarUri('S001'), 'blob:https://school.example/portrait-a');
assert.equal(anonymousAvatarUri('S001'), anonymous);

for (const invalid of ['https://cloud.example/photo.jpg', 'http://cloud.example/a', 'data:image/png;base64,abc', 'blob:', 'blob:bad" onload="attack', 'blob:bad\nurl']) {
  assert.throws(() => setDirectoryPortraits(new Map([['S002', 'blob:valid'], ['S001', invalid]])), TypeError);
  assert.equal(directoryPortraitUri('S001'), 'blob:https://school.example/portrait-a');
  assert.equal(directoryPortraitUri('S002'), null);
}
assert.throws(() => setDirectoryPortraits({ S001: 'blob:value' }), TypeError);

const image = avatarImg('S001', 'existing-avatar');
assert.equal(image.src, 'blob:https://school.example/portrait-a');
assert.equal(image.alt, 'Illustrative portrait for simulated student S001');
assert.equal(image.classList.contains('existing-avatar'), true);
assert.equal(image.classList.contains('directory-portrait'), true);
image.onerror();
assert.equal(image.src, anonymous);
assert.equal(image.alt, 'S001');
assert.equal(image.onerror, null);
assert.equal(image.classList.contains('directory-portrait'), false);

const staleImage = avatarImg('S001');
const oldError = staleImage.onerror;
staleImage.src = 'blob:new-source';
oldError();
assert.equal(staleImage.src, 'blob:new-source');

const bitmap = avatarBitmap('S001', 64);
assert.equal(images.at(-1).src, anonymous);
assert.equal(bitmap.dataset.ready, '0');
clearDirectoryPortraits();
assert.equal(directoryPortraitUri('S001'), null);
assert.equal(avatarUri('S001'), anonymous);
assert.equal(avatarBitmap('S001', 64), bitmap);
assert.equal(avatarImg('S001').alt, 'S001');

console.log('Avatar mapping checks passed: atomic local mappings, cloned inputs, anonymous fallback, stale-event guard, and independent bitmap cache.');
