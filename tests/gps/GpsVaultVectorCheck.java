import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.HexFormat;
import java.util.UUID;
import javax.crypto.AEADBadTagException;
import javax.crypto.Cipher;
import javax.crypto.spec.GCMParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/** Public synthetic interoperability harness; never use its key or nonce in an app. */
public final class GpsVaultVectorCheck {
    private static final byte[] PREFIX = "MF-GPS-V1\0".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] POINT = "minefleet-synthetic-point".getBytes(StandardCharsets.US_ASCII);
    private static final byte[] EXPECTED = HexFormat.of().parseHex(
        "2a6bb87ea389a77ef96ce4f2df9d1008f7bfe419801436124cf0bd5b566acb5eb4ff174d0e64adb1c4");
    private static final byte[] KEY = sequence(32);
    private static final byte[] NONCE = sequence(12);
    private static int checks;

    private static byte[] sequence(int size) {
        byte[] bytes = new byte[size];
        for (int i = 0; i < size; i++) bytes[i] = (byte) i;
        return bytes;
    }

    // tenant, account, session, site, vehicle, share, point (network byte order).
    private static byte[] aad(UUID[] scope) {
        if (scope.length != 7) throw new IllegalArgumentException("Invalid scope");
        ByteBuffer buffer = ByteBuffer.allocate(PREFIX.length + 7 * 16);
        buffer.put(PREFIX);
        for (UUID id : scope) {
            buffer.putLong(id.getMostSignificantBits());
            buffer.putLong(id.getLeastSignificantBits());
        }
        return buffer.array();
    }

    private static byte[] crypt(int mode, byte[] key, byte[] nonce, byte[] associated, byte[] input)
            throws Exception {
        Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
        cipher.init(mode, new SecretKeySpec(key, "AES"), new GCMParameterSpec(128, nonce));
        cipher.updateAAD(associated);
        return cipher.doFinal(input);
    }

    private static void verify(boolean condition) {
        if (!condition) throw new AssertionError("GPS vector mismatch");
        checks++;
    }

    private static void reject(byte[] key, byte[] nonce, byte[] associated, byte[] ciphertext)
            throws Exception {
        try {
            crypt(Cipher.DECRYPT_MODE, key, nonce, associated, ciphertext);
            throw new AssertionError("Modified vector accepted");
        } catch (AEADBadTagException expected) {
            checks++;
        }
    }

    public static void main(String[] args) throws Exception {
        UUID[] scope = new UUID[7];
        for (int i = 0; i < scope.length; i++) scope[i] = new UUID(0, i + 1);
        byte[] context = aad(scope);
        verify(context.length == 122);
        verify(Arrays.equals(crypt(Cipher.ENCRYPT_MODE, KEY, NONCE, context, POINT), EXPECTED));
        verify(Arrays.equals(crypt(Cipher.DECRYPT_MODE, KEY, NONCE, context, EXPECTED), POINT));

        for (int i = 0; i < scope.length; i++) {
            UUID[] changed = scope.clone();
            changed[i] = new UUID(0, 100 + i);
            reject(KEY, NONCE, aad(changed), EXPECTED);
            for (int j = i + 1; j < scope.length; j++) {
                UUID[] swapped = scope.clone();
                swapped[i] = scope[j];
                swapped[j] = scope[i];
                reject(KEY, NONCE, aad(swapped), EXPECTED);
            }
        }
        for (int i = 0; i < EXPECTED.length; i++) {
            byte[] changed = EXPECTED.clone();
            changed[i] ^= 1;
            reject(KEY, NONCE, context, changed);
        }
        byte[] nonce = NONCE.clone();
        nonce[0] ^= 1;
        reject(KEY, nonce, context, EXPECTED);
        byte[] version = context.clone();
        version[8] = '2';
        reject(KEY, NONCE, version, EXPECTED);
        byte[] key = KEY.clone();
        key[0] ^= 1;
        reject(key, NONCE, context, EXPECTED);
        try {
            aad(Arrays.copyOf(scope, 6));
            throw new AssertionError("Invalid scope accepted");
        } catch (IllegalArgumentException expected) {
            checks++;
        }
        System.out.println("GPS vault reference: " + checks + " checks passed");
    }
}
