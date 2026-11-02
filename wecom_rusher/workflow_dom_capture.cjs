'use strict';
// A screenshot is diagnostic evidence, never the application's commit receipt.
async function captureDiagnostic(page, file, recheckIdentity, recordEvent) {
  try {
    await page.screenshot({path: file, timeout: 5000});
  } catch (error) {
    if (!error || error.name !== 'TimeoutError') throw error;
    // No raw exception, path, workflow value or locator is written to this log.
    recordEvent({event: 'diagnostic_screenshot_timeout'});
  }
  // Do not turn a screenshot timeout into permission to ignore a changed page.
  await recheckIdentity();
}
module.exports = {captureDiagnostic};
