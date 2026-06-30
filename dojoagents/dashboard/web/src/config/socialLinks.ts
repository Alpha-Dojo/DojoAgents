import discordIcon from '../assets/svg/discord.svg';
import githubIcon from '../assets/svg/github.svg';
import huggingfaceIcon from '../assets/svg/huggingface.svg';
import wechatIcon from '../assets/svg/wechat.svg';

export const SOCIAL_LINKS = [
  {
    key: 'huggingface',
    label: 'Hugging Face',
    href: 'https://huggingface.co/AlphaDojo',
    icon: huggingfaceIcon,
  },
  {
    key: 'github',
    label: 'GitHub',
    href: 'https://github.com/Alpha-Dojo/DojoAgents',
    icon: githubIcon,
  },
  {
    key: 'discord',
    label: 'Discord',
    href: 'https://discord.gg/CCRvSvdvr',
    icon: discordIcon,
  },
  {
    key: 'wechat',
    label: 'WeChat',
    href: '',
    icon: wechatIcon,
  },
] as const;

export const WECHAT_QR_IMAGE: string | null = null;
