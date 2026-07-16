import { ConfigProvider, DatePicker, theme } from 'antd';
import enUS from 'antd/es/date-picker/locale/en_US';
import zhCN from 'antd/es/date-picker/locale/zh_CN';
import dayjs, { type Dayjs } from 'dayjs';
import 'dayjs/locale/zh-cn';
import { useTranslation } from '../../hooks/useTranslation';

const ISO_DATE_FORMAT = 'YYYY-MM-DD';
const FOLIO_DATE_PICKER_THEME = {
  algorithm: theme.darkAlgorithm,
  token: {
    colorPrimary: '#02af7f',
    colorPrimaryHover: '#00e0a2',
    colorPrimaryActive: '#03835f',
    colorBgBase: '#070f15',
    colorBgContainer: '#0b1824',
    colorBgElevated: '#0b1824',
    colorText: '#ffffff',
    colorTextSecondary: '#94a3b8',
    colorTextDisabled: '#64748b',
    colorBorder: 'rgb(255 255 255 / 10%)',
    colorSplit: 'rgb(255 255 255 / 10%)',
    borderRadius: 4,
  },
  components: {
    DatePicker: {
      activeBorderColor: '#02af7f',
      hoverBorderColor: '#00e0a2',
      activeShadow: '0 0 0 2px rgb(0 224 162 / 32%)',
      cellHoverBg: 'rgb(2 175 127 / 16%)',
    },
  },
} as const;

interface FolioDatePickerProps {
  value: string;
  minDate: string;
  maxDate: string;
  className: string;
  disabled?: boolean;
  title?: string;
  ariaLabel?: string;
  disabledDate?: (current: Dayjs) => boolean;
  onChange: (value: string) => void;
}

export function FolioDatePicker({
  value,
  minDate,
  maxDate,
  className,
  disabled = false,
  title,
  ariaLabel,
  disabledDate,
  onChange,
}: FolioDatePickerProps) {
  const { locale, t } = useTranslation();

  return (
    <ConfigProvider theme={FOLIO_DATE_PICKER_THEME}>
      <DatePicker
        className={className}
        classNames={{ popup: { root: 'folio-table__date-popup' } }}
        value={dayjs(value, ISO_DATE_FORMAT)}
        minDate={dayjs(minDate, ISO_DATE_FORMAT)}
        maxDate={dayjs(maxDate, ISO_DATE_FORMAT)}
        format={ISO_DATE_FORMAT}
        locale={locale === 'zh' ? zhCN : enUS}
        aria-label={ariaLabel ?? t('folio.colOpenDate')}
        disabled={disabled}
        title={title}
        allowClear={false}
        disabledDate={disabledDate}
        onChange={(date) => onChange(date?.format(ISO_DATE_FORMAT) ?? '')}
      />
    </ConfigProvider>
  );
}
