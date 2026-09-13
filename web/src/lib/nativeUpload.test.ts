import assert from 'node:assert/strict'
import { describe, it } from 'node:test'
import {
  IOS_SETTINGS_ACCESS,
  isPermissionDenied,
  isUserCancel,
  READING_LIST_TYPE_LIMIT,
} from './nativeUpload'

describe('native Promote upload errors', () => {
  it('maps a camera/photos denial to the Settings recovery message', () => {
    assert.equal(isPermissionDenied(new Error('User denied access to camera')), true)
    assert.equal(isPermissionDenied(new Error('permission denied')), true)
    assert.equal(isPermissionDenied(new Error('network down')), false)
    assert.equal(IOS_SETTINGS_ACCESS.includes('Settings → BadgeDay'), true)
  })

  it('does not treat a cancelled picker as a failure', () => {
    assert.equal(isUserCancel(new Error('User cancelled photos app')), true)
    assert.equal(isUserCancel(new Error('that file is empty')), false)
  })

  it('states the existing PDF/DOCX limit when a capture cannot be uploaded', () => {
    assert.match(READING_LIST_TYPE_LIMIT, /PDF or a Word document/)
  })
})
