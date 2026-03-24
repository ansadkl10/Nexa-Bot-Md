import axios from 'axios';
import FormData from 'form-data';

const uploadToCatbox = async (buffer, fileName) => {
    const formData = new FormData();
    formData.append('reqtype', 'fileupload');
    formData.append('fileToUpload', buffer, { filename: fileName });

    const response = await axios.post('https://catbox.moe/user/api.php', formData, {
        headers: { ...formData.getHeaders() }
    });

    return response.data; 
};

export default uploadToCatbox;
