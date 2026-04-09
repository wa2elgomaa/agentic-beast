
interface LogoProps extends React.SVGProps<SVGSVGElement> {
  color?: string
}


const LogoIcon = ({ color, ...props }: LogoProps) => <svg
  height={50}
  width={50}
  version="1.1"
  xmlns="http://www.w3.org/2000/svg"
  xmlnsXlink="http://www.w3.org/1999/xlink"
  viewBox="0 0 378 377"
  xmlSpace="preserve"
  {...props}
>
  <g xmlns="http://www.w3.org/2000/svg">
    <path d="M 0.00 0.00 L 60.00 0.00 L 60.00 377.00 L 0.00 377.00 Z" fill="rgb(0,78,119)" />
    <path d="M 128.16 0.00 L 246.00 0.00 L 246.00 93.50 C246.00,144.93 245.66,187.00 245.25,187.00 C244.83,187.00 218.20,160.70 186.06,128.56 L 127.63 70.13 L 127.90 35.06 ZM 246.00 377.00 L 128.00 377.00 L 128.00 284.00 C128.00,232.85 128.34,191.00 128.75,191.00 C129.16,191.00 155.71,217.21 187.75,249.25 L 246.00 307.49 Z" fill="rgb(127,164,185)" />
    <path d="M 316.00 377.00 L 316.00 83.00 L 378.00 83.00 L 378.00 377.00 L 316.00 377.00 ZM 378.00 0.00 L 378.00 51.00 L 316.00 51.00 L 316.00 0.00 Z" fill="rgb(129,170,250)" />
  </g>
</svg>

export default LogoIcon;
