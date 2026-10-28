// Fewer, longer byte ranges for the differential download. github.com takes one range per request (updater.js,
// ReleaseProvider), and each request costs about 0.7 s of redirects and round trips, 3-4 MB at the speed a whole
// installer downloads. electron-updater asks for every run of changed blocks on its own: 0.6.0 to 0.6.1 took 117
// requests for 8.7 MB, 77 s against 28 s for the whole 157 MB. Changed runs closer than MERGE_GAP are fetched as one
// range, the unchanged bytes between them included (6 requests for 12.4 MB on that update).
//
// Then the ranges are fetched at the same time rather than one after another: 0.7.0 to 0.8.0 still took 8.4 s for
// 12.8 MB in 6 requests, 1.5 MB/s against 5.7 MB/s for a whole download (user report, 2026-10-28); the same six
// ranges from GitHub took 7.0 and 7.9 s one after another, 5.3 and 3.8 s all at once. electron-updater's own pass
// then reads them from memory, so its copying from the old installer and its sha512 check are unchanged.

const { EventEmitter } = require('node:events');
const { Readable } = require('node:stream');
const plan = require('electron-updater/out/differentialDownloader/downloadPlanBuilder');
const { DifferentialDownloader } = require('electron-updater/out/differentialDownloader/DifferentialDownloader');

const MERGE_GAP = 1024 * 1024;
const AT_ONCE = 4;
const { COPY, DOWNLOAD } = plan.OperationKind;

// Operations run in the new file's order; a download's start and end are new-file offsets and a copy's length is the
// same in both files, so download, short copy, download is one download from the first start to the last end.
function mergeNearby(operations, gap = MERGE_GAP) {
  const merged = [];
  for (const operation of operations) {
    const copy = merged.at(-1);
    const before = merged.at(-2);
    const length = copy && copy.end - copy.start;
    if (operation.kind === DOWNLOAD && copy?.kind === COPY && before?.kind === DOWNLOAD && length <= gap &&
        before.end + length === operation.start) {
      merged.pop();
      before.end = operation.end;
    } else {
      merged.push({ ...operation });
    }
  }
  return merged;
}

const ranges = (operations) => operations.filter((operation) => operation.kind === DOWNLOAD).length;

// Fetches every range to download, AT_ONCE at a time, reporting progress as electron-updater would.
async function fetchAll(downloader, tasks) {
  const wanted = tasks.filter((task) => task.kind === DOWNLOAD);
  const total = wanted.reduce((sum, task) => sum + task.end - task.start, 0);
  const report = downloader.options.onProgress;
  const started = Date.now();
  let transferred = 0;
  const parts = new Map();
  const fetchOne = (task) => {
    const options = downloader.createRequestOptions();
    options.headers.range = `bytes=${task.start}-${task.end - 1}`;
    const chunks = [];
    return downloader
      .request(options, (chunk) => {
        chunks.push(chunk);
        transferred += chunk.length;
        const seconds = Math.max((Date.now() - started) / 1000, 0.001);
        report?.({ total, delta: chunk.length, transferred, percent: (transferred / total) * 100, bytesPerSecond: transferred / seconds });
      })
      .then(() => {
        const data = Buffer.concat(chunks);
        if (data.length !== task.end - task.start) throw new Error(`range ${options.headers.range}: ${data.length} bytes`);
        parts.set(options.headers.range, data);
      });
  };
  const queue = [...wanted];
  await Promise.all(Array.from({ length: Math.min(AT_ONCE, queue.length) }, async () => {
    while (queue.length) await fetchOne(queue.shift());
  }));
  return parts;
}

// An HTTP executor that answers range requests from memory, for electron-updater's own pass over the plan.
function fromMemory(executor, parts) {
  return Object.assign(Object.create(executor), {
    createRequest(options, callback) {
      const request = new EventEmitter();
      request.followRedirect = () => {};
      request.abort = () => {};
      request.end = () => {
        const data = parts.get(options.headers.range);
        setImmediate(() => {
          if (!data) return request.emit('error', new Error(`no fetched data for ${options.headers.range}`));
          const response = Readable.from([data]);
          Object.assign(response, { statusCode: 206, headers: {} });
          callback(response);
        });
      };
      return request;
    },
  });
}

// electron-updater's DifferentialDownloader reads computeOperations from the module on every download.
function install() {
  if (plan.computeOperations.merging) return;
  const downloadFile = DifferentialDownloader.prototype.downloadFile;
  DifferentialDownloader.prototype.downloadFile = async function (tasks) {
    if (this.options.isUseMultipleRangeRequest) return downloadFile.call(this, tasks);
    const parts = await fetchAll(this, tasks);
    const { httpExecutor } = this;
    const report = this.options.onProgress;
    this.httpExecutor = fromMemory(httpExecutor, parts);
    this.options.onProgress = undefined; // progress was reported while fetching
    try {
      return await downloadFile.call(this, tasks);
    } finally {
      this.httpExecutor = httpExecutor;
      this.options.onProgress = report;
    }
  };
  const compute = plan.computeOperations;
  const merging = (oldBlockMap, newBlockMap, logger) => {
    const operations = compute(oldBlockMap, newBlockMap, logger);
    const merged = mergeNearby(operations);
    logger.info(`${ranges(operations)} ranges to download, ${ranges(merged)} after joining gaps up to ${MERGE_GAP / 1024} KB`);
    return merged;
  };
  merging.merging = true;
  plan.computeOperations = merging;
}

module.exports = { mergeNearby, install, MERGE_GAP };
