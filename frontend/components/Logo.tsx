
interface LogoProps extends React.SVGProps<SVGSVGElement> {
  color?: string
}


const LogoIcon = ({ color, ...props }: LogoProps) => <svg
  height={50}
  width={50}
  version="1.1"
  xmlns="http://www.w3.org/2000/svg"
  xmlnsXlink="http://www.w3.org/1999/xlink"
  x="0px"
  y="0px"
  viewBox="0 0 1000 1000"
  style={{ enableBackground: 'new 0 0 1000 1000' }}
  xmlSpace="preserve"
  {...props}
>
  <g>
    <path fill={color} d="M0.4,1000h281.3V843.7h-125V156.1h125V-0.2H0.4V1000z M1000.6,1000V-0.2H719.3v156.3h125v687.6h-125V1000
       H1000.6z"/>
    <path fill={color} d="M344.2,156.1l312.6,343.8V-0.2H344.2V156.1z M656.8,1000V843.7L344.2,499.9V1000H656.8z" />
  </g>
</svg>

export default LogoIcon;
