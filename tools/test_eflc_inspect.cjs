// Synthetic discs only; no game files are required or included.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const { webcrypto } = require('node:crypto');
const html = fs.readFileSync(__dirname + '/eflc-inspect.html', 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const context = vm.createContext({Blob, TextEncoder, TextDecoder, Uint8Array, Uint32Array, DataView, Set, crypto:webcrypto, document:{getElementById(){return {addEventListener(){}};}}});
vm.runInContext(script, context);
function fixture({base = 0, size = base + 200000, mutate = () => {}} = {}) {
  const data = Buffer.alloc(200000);
  data.write('MICROSOFT*XBOX*MEDIA', 65536);
  data.writeUInt32LE(40, 65556); data.writeUInt32LE(128, 65560);
  function entry(at, name, sector, length, attributes = 0, right = 0) {
    data.writeUInt16LE(right, at + 2); data.writeUInt32LE(sector, at + 4); data.writeUInt32LE(length, at + 8);
    data[at + 12] = attributes; data[at + 13] = name.length; data.write(name, at + 14);
  }
  entry(40 * 2048, 'default.xex', 50, 128, 0, 16);
  entry(40 * 2048 + 64, 'episode', 60, 64, 0x10);
  entry(60 * 2048, 'other.xex', 70, 128);
  for (const sector of [50, 70]) {
    const at = sector * 2048;
    data.write('XEX2', at); data.writeUInt32BE(1, at + 4); data.writeUInt32BE(128, at + 8); data.writeUInt32BE(1, at + 20);
    data.writeUInt32BE(0x40006, at + 24); data.writeUInt32BE(48, at + 28);
    data.writeUInt32BE(0x06759F9C, at + 48); data.writeUInt32BE(10, at + 52); data.writeUInt32BE(10, at + 56); data.writeUInt32BE(0x545407F2, at + 60);
  }
  mutate(data);
  const file = {name:'synthetic.iso', size, slice(start, end) {
    const result = Buffer.alloc(end - start);
    const from = Math.max(start, base), to = Math.min(end, base + data.length);
    if (from < to) data.copy(result, from - start, from - base, to - base);
    return new Blob([result]);
  }};
  return file;
}
(async () => {
  let passed = 0;
  const run = async (name, fn) => { await fn(); passed++; process.stdout.write('PASS ' + name + '\n'); };
  await run('nested files, XEX metadata, SHA256 and ZIP', async () => {
    const result = await context.makeBundle(fixture());
    assert.equal(result.report.compatibility, 'unverified'); assert.equal(result.report.executables.length, 2);
    assert.equal(result.report.executables[0].metadata.mediaId, '06759F9C');
    assert.equal(result.report.executables[0].metadata.version, '0000000A');
    assert.equal(result.report.executables[0].sha256.length, 64);
    fs.writeFileSync(process.env.EFLC_TEST_ZIP || '/tmp/eflc-synthetic-test.zip', Buffer.from(await result.zip.arrayBuffer()));
  });
  for (const base of [0xFB20, 0x20600, 0x2080000, 0xFD90000]) {
    await run('partition offset ' + base.toString(16), async () => assert.equal((await context.listIso(fixture({base}))).partitionOffset, base));
  }
  await run('disc larger than 4 GiB, bounded reads', async () => {
    const file = fixture({base:0xFD90000, size:8 * 1024 ** 3}); let read = 0;
    const original = file.slice; file.slice = (a,b) => { read += b-a; return original(a,b); };
    assert.equal((await context.makeBundle(file)).report.iso.size, 8 * 1024 ** 3);
    assert.ok(read < 20000);
  });
  const reject = (mutate, pattern) => assert.rejects(context.listIso(fixture({mutate})), pattern);
  await run('directory node cycle', () => reject(d => d.writeUInt16LE(16, 40*2048+64+2), /cyclische/));
  await run('parent directory cycle', () => reject(d => {d.writeUInt32LE(40, 40*2048+64+4);d.writeUInt32LE(128, 40*2048+64+8);}, /cyclische/));
  await run('file range outside ISO', () => reject(d => d.writeUInt32LE(0xFFFFFFFF, 40*2048+4), /buiten/));
  await run('unsafe filename', () => reject(d => d.write('../evil.xex', 40*2048+14), /bestandsnaam/));
  await run('truncated name', () => reject(d => {d.writeUInt32LE(24, 65560);d[40*2048+13]=50;}, /bestandsnaam/));
  await run('invalid disc header', () => reject(d => d[65536]=0, /discindeling/));
  await run('missing executables', async () => assert.rejects(context.makeBundle(fixture({mutate:d=>{d.write('default.txt',40*2048+14);d.write('other.txt',60*2048+14);}})), /Geen .xex/));
  await run('oversized executable blocked before reading', async () => {
    const file=fixture({size:8*1024**3,mutate:d=>d.writeUInt32LE(65*1024**2,40*2048+8)});
    await assert.rejects(context.makeBundle(file), /onverwacht groot/);
  });
  await run('malformed execution offset', async () => {
    const result=await context.makeBundle(fixture({mutate:d=>d.writeUInt32BE(120,50*2048+28)}));
    assert.equal(result.report.executables[0].metadata.error,'Ongeldige execution-info');
  });
  await run('CRC32 reference vector', async () => assert.equal(context.crc32(new TextEncoder().encode('123456789')),0xCBF43926));
  await run('asset request reports missing archives', async () => assert.rejects(context.makeBundle(fixture(),()=>{},true), /ontbreken/));
  await run('asset bundle includes required archives and update shaders', async () => {
    const original=context.listIso;
    context.listIso=async()=>({partitionOffset:0,rootSector:40,rootSize:128,entries:[
      {path:'default.xex',offset:50*2048,size:128,directory:false},
      ...['common.rpf','xbox360.rpf','DLC1/DLC.rpf','DLC2/DLC.rpf','DLC1/DLC/common/data/cdimages/script.img','DLC2/DLC/common/data/cdimages/script.img','update/shaders/fxl_final/rage_postfx_e2.fxc'].map(path=>({path,offset:50*2048,size:16,directory:false})),
      {path:'xbox360/audio/sfx/huge.rpf',offset:0,size:150*1024**2,directory:false}
    ]});
    try {
      const result=await context.makeBundle(fixture(),()=>{},true);
      assert.equal(result.report.includesResearchAssets,true);
      fs.writeFileSync('/tmp/eflc-synthetic-assets-test.zip',Buffer.from(await result.zip.arrayBuffer()));
    } finally {context.listIso=original;}
  });
  process.stdout.write(passed + ' checks passed\n');
})().catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1;});
