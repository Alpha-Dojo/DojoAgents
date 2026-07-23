class FinancialGatewaySurface:
    def __init__(self, service_container):
        self.service_container = service_container

    @property
    def services(self):
        return self.service_container


__all__ = ["FinancialGatewaySurface"]
