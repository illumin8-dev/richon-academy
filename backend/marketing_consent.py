"""Optional advertising-message consent. Default OFF until DB011 is prepared."""
import os

VERSION='marketing-v1'
CHANNELS=('email','sms')
ENV='RICHON_MARKETING_CONSENT_ENABLED'


def enabled():
    return os.getenv(ENV,'false')=='true'
