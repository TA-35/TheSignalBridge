// One shared password for the whole site, checked at the CloudFront edge.
//
// This has to live here, not in nginx: the frontend is a private S3 bucket
// behind CloudFront (distribution E1YGUMFRDSPNVG, aliases thesignalbridge.com
// and www.thesignalbridge.com). The EC2 box in infra/nginx/ only ever serves
// api.thesignalbridge.com, so auth_basic there never sees website traffic.
//
// __BASIC_AUTH_TOKEN__ is a placeholder, on purpose - the real credentials are
// never committed. publish.sh substitutes base64("user:password") from the
// environment at publish time, so the deployed function and this file
// deliberately differ. Run publish.sh to change the password; see "Shared
// website password" in the README.
//
// 401 on purpose, never 403: the distribution rewrites 403 and 404 to
// /index.html with a 200 for SPA routing, which would swallow the challenge.
// Viewer-request responses skip that rewrite, but only for other status codes.

var EXPECTED = 'Basic __BASIC_AUTH_TOKEN__';

function handler(event) {
    var headers = event.request.headers;

    if (headers.authorization && headers.authorization.value === EXPECTED) {
        return event.request;
    }

    return {
        statusCode: 401,
        statusDescription: 'Unauthorized',
        headers: {
            'www-authenticate': { value: 'Basic realm="TheSignalBridge", charset="UTF-8"' },
            'cache-control': { value: 'no-store' }
        }
    };
}
