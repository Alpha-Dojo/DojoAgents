import { defineStore } from 'pinia';

interface QuantContext {
  market: string;
  symbols: string[];
  sector_path: string[];
  portfolio_id: string | null;
  dashboard_tab: string;
}

export const useFinancialContextStore = defineStore('financialContext', {
  state: (): QuantContext => ({
    market: 'us',
    symbols: [],
    sector_path: [],
    portfolio_id: null,
    dashboard_tab: 'dojo-core'
  }),
  actions: {
    setMarket(market: string) {
      this.market = market;
    },
    setSymbols(symbols: string[]) {
      this.symbols = symbols;
    },
    setSectorPath(path: string[]) {
      this.sector_path = path;
    },
    setPortfolio(id: string | null) {
      this.portfolio_id = id;
    },
    setTab(tab: string) {
      this.dashboard_tab = tab;
    }
  }
});
