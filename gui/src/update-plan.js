// Fewer, longer byte ranges for the differential download. github.com takes one range per request (updater.js,
// ReleaseProvider), and each request costs about 0.7 s of redirects and round trips, 3-4 MB at the speed a whole
// installer downloads. electron-updater asks for every run of changed blocks on its own: 0.6.0 to 0.6.1 took 117
// requests for 8.7 MB, 77 s against 28 s for the whole 157 MB. Changed runs closer than MERGE_GAP are fetched as one
// range, the unchanged bytes between them included (6 requests for 12.4 MB on that update).

const plan = require('electron-updater/out/differentialDownloader/downloadPlanBuilder');

const MERGE_GAP = 1024 * 1024;
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

// electron-updater's DifferentialDownloader reads computeOperations from the module on every download.
function install() {
  if (plan.computeOperations.merging) return;
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
